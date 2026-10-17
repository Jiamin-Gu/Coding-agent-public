"""Docker 沙箱：agent 的命令（run_command、后台进程）在容器里执行，而不是直接在用户的电脑上。

容器的限制：
- 只挂载工作区（容器里是 /workspace），看不到用户的其他文件（~/.ssh、浏览器数据等）
- 默认断网。命令需要联网时（安装依赖），由用户单独确认，执行期间临时接入网络，结束后断开
- 非 root 用户、去掉所有 Linux capabilities、禁止提权、根文件系统只读（/tmp 是内存盘）
- 限制内存、CPU 和进程数，防止失控的程序拖垮电脑
- 家目录挂持久卷：pip --user、npm 全局安装和缓存都在里面，重建容器不用重新下载

读写文件的工具（read_file、write_file 等）仍然在本机执行，它们本来就只能访问工作区（路径沙箱）。

每个会话一个常驻容器（第一次执行命令时启动），命令用 docker exec 执行，速度接近本机。
命令在容器里自成进程组，停止时在容器里整组终止：只杀掉本机的 docker exec 客户端，容器里的进程还会继续运行。

命令行：python -m coder.sandbox build | status | clean
"""
import atexit
import itertools
import os
import shutil
import subprocess
import sys
import threading
import uuid
from pathlib import Path

from .portforward import PortForwarder
from .tools.base import ToolError

IMAGE = "coder-sandbox:1"
HOME_VOLUME = "coder-sandbox-home"
DOCKERFILE_DIR = Path(__file__).resolve().parent / "sandbox_image"  # 放在包里，pip 安装后也能构建
LABEL = "coder.sandbox=1"
LIMITS = ["--memory", "4g", "--cpus", "4", "--pids-limit", "512"]
# Docker Desktop 装好后要重新打开终端 PATH 才会生效，找不到时去默认安装位置找
DOCKER_CANDIDATES = [
    Path(os.getenv("LOCALAPPDATA", "")) / "Programs/DockerDesktop/resources/bin/docker.exe",
    Path(os.getenv("ProgramFiles", "C:/Program Files")) / "Docker/Docker/resources/bin/docker.exe",
    Path("/usr/local/bin/docker"), Path("/opt/homebrew/bin/docker"),
]

# 在容器里启动命令：自成进程组（setsid），记下进程组号，停止时整组终止
LAUNCH = 'mkdir -p /tmp/.coder && echo $$ > /tmp/.coder/{token}.pid && exec bash -c "$1"'
KILL = ('p=$(cat /tmp/.coder/{token}.pid 2>/dev/null) || exit 0; '
        'kill -TERM -- -$p 2>/dev/null; sleep 0.5; kill -KILL -- -$p 2>/dev/null; rm -f /tmp/.coder/{token}.pid')

ENVIRONMENT = """Linux (Debian 12) inside a Docker sandbox container; commands run via /bin/bash
- The workspace is mounted at /workspace, which is the current directory for commands. \
Use relative paths in commands (file tools still take paths relative to the workspace root).
- Available: Python 3.12 (pip install --user), Node.js 22 + npm, git, gcc/make, curl, ripgrep, jq.
- The sandbox has NO network access by default. If a command really needs the network (installing \
dependencies, downloading), call run_command / start_process with network=true; the user will be asked to approve.
- Only files under /workspace persist on the user's machine; you cannot use sudo or apt-get
- Servers you start with start_process are forwarded to the user's machine automatically; the tool result shows \
the preview URL (http://127.0.0.1:PORT). Give that URL to the user when they should look at the app."""


def find_docker() -> str | None:
    found = shutil.which("docker")
    if found:
        return found
    return next((str(p) for p in DOCKER_CANDIDATES if p.is_file()), None)


def _no_window() -> dict:
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}


def pid_alive(pid: int) -> bool:
    """进程是否还在运行。Windows 上不能用 os.kill(pid, 0)：那会直接结束目标进程。"""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        kernel32.CloseHandle(handle)
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def remove_orphans(docker: str) -> int:
    """删除启动它的 coder 进程已经不在的容器（比如直接关掉了终端窗口，没来得及清理）。返回删除的个数。"""
    r = subprocess.run([docker, "ps", "-a", "--filter", f"label={LABEL}", "--format", '{{.ID}} {{.Label "coder.pid"}}'],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, **_no_window())
    dead = [cid for cid, _, pid in (line.partition(" ") for line in r.stdout.splitlines())
            if not (pid.strip().isdigit() and pid_alive(int(pid)))]
    if dead:
        subprocess.run([docker, "container", "rm", "-f", *dead], capture_output=True, timeout=60, **_no_window())
    return len(dead)


def docker_status(image: str = IMAGE) -> tuple[bool, str]:
    """沙箱能不能用：(可用, 说明)。说明写给用户看，告诉他怎么解决。"""
    docker = find_docker()
    if not docker:
        return False, "没有找到 Docker。请先安装 Docker Desktop：https://www.docker.com/products/docker-desktop/"
    r = subprocess.run([docker, "info", "--format", "{{.ServerVersion}}"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=30, **_no_window())
    if r.returncode != 0 or not r.stdout.strip():
        return False, "Docker 没有在运行：请打开 Docker Desktop，等它启动完成后再试"
    r = subprocess.run([docker, "image", "inspect", image], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=30, **_no_window())
    if r.returncode != 0:
        return False, f"还没有沙箱镜像 {image}：请运行 python -m coder.sandbox build（只需构建一次）"
    return True, f"Docker 正常，镜像 {image} 已就绪"


class DockerSandbox:
    """一个会话的沙箱容器。接口和本机执行一致：popen(命令) 启动、kill(进程) 整组终止。"""
    supports_network = True  # 默认断网，命令可以申请临时联网

    def __init__(self, root: str | Path, image: str = IMAGE, env: dict[str, str] | None = None):
        self.root = Path(root).resolve()
        self.image = image
        self.env = env or {}  # 容器的环境变量（比如评测时用指定的 Python 虚拟环境）
        self.docker = find_docker()
        self.name = f"coder-sbx-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self.started = False
        self.lock = threading.Lock()
        self._net_users = 0          # 正在使用网络的命令数，降到 0 时断网
        self._tokens = itertools.count(1)
        self.forwarder = PortForwarder(self)  # 把容器里的开发服务器转发到本机，方便预览

    # ---------- 容器生命周期 ----------

    def _docker(self, *args, check: bool = True, timeout: int = 60) -> subprocess.CompletedProcess:
        r = subprocess.run([self.docker, *args], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, **_no_window())
        if check and r.returncode != 0:
            raise ToolError(f"Docker 命令失败（docker {' '.join(args[:2])}）：{(r.stderr or r.stdout).strip()[:500]}")
        return r

    def run_args(self) -> list[str]:
        """启动常驻容器的参数（单独拿出来，方便测试检查安全设置）。"""
        return ["run", "-d", "--name", self.name, "--label", LABEL, "--label", f"coder.pid={os.getpid()}",
                "--init", "--read-only", "--tmpfs", "/tmp:rw,exec,size=1g",
                "--cap-drop", "ALL", "--security-opt", "no-new-privileges", *LIMITS,
                "-v", f"{self.root}:/workspace", "-v", f"{HOME_VOLUME}:/home/coder", "-w", "/workspace",
                *[x for k, v in self.env.items() for x in ("-e", f"{k}={v}")],
                self.image, "sleep", "infinity"]

    def ensure_started(self) -> None:
        with self.lock:
            if self.started:
                return
            if not self.docker:
                raise ToolError(docker_status(self.image)[1])
            remove_orphans(self.docker)
            r = self._docker(*self.run_args(), check=False)
            if r.returncode != 0:
                ok, why = docker_status(self.image)
                raise ToolError(f"沙箱启动失败：{why if not ok else r.stderr.strip()[:500]}")
            self.started = True
            _running.add(self)  # 强引用：会话对象被回收后，程序退出时也要能找到它删掉容器
            # 用默认网络启动再断开（--network none 的容器之后接不上网络），需要联网时再临时接入
            self._docker("network", "disconnect", "bridge", self.name, check=False)

    def stop(self) -> None:
        self.forwarder.stop_all()
        with self.lock:
            if self.started:
                self._docker("container", "rm", "-f", self.name, check=False)
                self.started = False
                self._net_users = 0
            _running.discard(self)

    # ---------- 网络 ----------

    def _net_acquire(self) -> None:
        with self.lock:
            if self._net_users == 0:
                self._docker("network", "connect", "bridge", self.name)
            self._net_users += 1

    def _net_release(self) -> None:
        with self.lock:
            self._net_users = max(0, self._net_users - 1)
            if self._net_users == 0 and self.started:
                self._docker("network", "disconnect", "bridge", self.name, check=False)

    # ---------- 执行命令（和 tools/shell.py 的 popen_tree / kill_tree 对应） ----------

    def popen(self, command: str, cwd=None, network: bool = False) -> subprocess.Popen:
        self.ensure_started()
        token = f"t{next(self._tokens)}"
        if network:
            self._net_acquire()
        args = [self.docker, "exec", "-w", "/workspace", self.name,
                "setsid", "-w", "bash", "-c", LAUNCH.format(token=token), "_", command]  # -w：等命令结束，带回退出码
        try:
            proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, **_no_window())
        except BaseException:
            if network:
                self._net_release()
            raise
        proc.coder_token = token
        proc.coder_network = network
        return proc

    def finished(self, proc: subprocess.Popen) -> None:
        """命令结束后调用：归还网络。重复调用没有影响。"""
        if getattr(proc, "coder_network", False):
            proc.coder_network = False
            self._net_release()

    def kill(self, proc: subprocess.Popen) -> None:
        if proc.poll() is None and self.started:
            self._docker("exec", self.name, "bash", "-c", KILL.format(token=proc.coder_token), check=False)
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(5)
        self.finished(proc)


_running: set[DockerSandbox] = set()  # 已经启动了容器的沙箱


@atexit.register
def _cleanup() -> None:  # 程序退出时删除本进程启动的容器
    for s in list(_running):
        try:
            s.stop()
        except Exception:
            pass


# ---------- 命令行 ----------

def build(image: str = IMAGE, apt_mirror: str = "") -> int:
    docker = find_docker()
    if not docker:
        print(docker_status(image)[1])
        return 1
    args = [docker, "build", "-t", image, str(DOCKERFILE_DIR)]
    if apt_mirror:
        args[2:2] = ["--build-arg", f"APT_MIRROR={apt_mirror}"]
    print("构建沙箱镜像（第一次需要下载约 370MB，之后只用本地缓存）……", flush=True)
    return subprocess.call(args)


def clean() -> int:
    """删除所有 coder 启动的沙箱容器，包括还在运行的会话的（启动新沙箱时只会自动删掉没人用的）。持久卷保留。"""
    docker = find_docker()
    if not docker:
        print(docker_status()[1])
        return 1
    ids = subprocess.run([docker, "ps", "-aq", "--filter", f"label={LABEL}"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.split()
    if ids:
        subprocess.run([docker, "container", "rm", "-f", *ids], capture_output=True)
    print(f"已删除 {len(ids)} 个沙箱容器")
    return 0


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(prog="python -m coder.sandbox", description="管理 coder 的 Docker 沙箱")
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="构建沙箱镜像")
    b.add_argument("--apt-mirror", default="", help="Debian 软件源镜像，例如 mirrors.tuna.tsinghua.edu.cn")
    sub.add_parser("status", help="检查 Docker 和镜像是否就绪")
    sub.add_parser("clean", help="删除残留的沙箱容器")
    args = parser.parse_args()
    if args.cmd == "build":
        sys.exit(build(apt_mirror=args.apt_mirror))
    if args.cmd == "clean":
        sys.exit(clean())
    ok, why = docker_status()
    print(why)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
