"""命令执行工具。"""
import locale
import os
import re
import signal
import subprocess

from .base import Tool, ToolError

# 无论什么权限模式都直接拒绝的命令。注意：这只是兜底，不是真正的安全隔离，
# 真正的隔离需要容器/虚拟机（见 README 路线图）。
DANGEROUS_PATTERNS = [
    r"\brm\s+-[a-z]*r[a-z]*f?\s+(/|~|\*)",   # rm -rf / ~ *
    r"\b(rd|rmdir)\s+/s\b",                 # Windows 递归删除
    r"\bdel\s+/[a-z]*s",                     # del /s
    r"\bformat\s+[a-z]:",
    r"\b(shutdown|reboot|mkfs)\b",
    r"\bgit\s+push\b.*--force",
]


def check_dangerous(command: str) -> None:
    for pat in DANGEROUS_PATTERNS:
        if re.search(pat, command, re.IGNORECASE):
            raise ToolError(f"命令被安全策略拒绝（匹配 {pat}）")


def popen_tree(command: str, cwd) -> subprocess.Popen:
    """启动命令，并让它自成一个进程组，之后可以整组终止。"""
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(command, shell=True, cwd=cwd, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kwargs)


def kill_tree(proc: subprocess.Popen) -> None:
    """终止进程和它启动的所有子进程（shell=True 时真正的程序是 shell 的子进程，只杀 shell 会留下孤儿进程）。"""
    if proc.poll() is None:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        else:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(3)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    try:
        proc.wait(5)
    except subprocess.TimeoutExpired:
        proc.kill()


class LocalExecutor:
    """在本机执行命令。沙箱模式下换成 sandbox.DockerSandbox，接口相同。"""
    supports_network = False  # 本机命令本来就能联网，不需要单独申请

    def popen(self, command: str, cwd, network: bool = False) -> subprocess.Popen:
        return popen_tree(command, cwd)

    def kill(self, proc: subprocess.Popen) -> None:
        kill_tree(proc)

    def finished(self, proc: subprocess.Popen) -> None:
        pass


LOCAL = LocalExecutor()

NETWORK_PARAM = {"type": "boolean", "default": False,
                 "description": "沙箱默认断网。命令确实需要联网（安装依赖、下载）时设为 true，会单独请用户确认"}


def decode(data: bytes) -> str:
    # Windows 中文系统下很多命令输出 GBK，不是 UTF-8
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode(locale.getpreferredencoding(False), errors="replace")


class RunCommand(Tool):
    name = "run_command"
    description = (
        "在工作区根目录执行 shell 命令，返回退出码和输出（stdout+stderr）。"
        "用于运行测试、构建、安装依赖、git 等。不要运行需要交互输入的命令；"
        "开发服务器、watch 这类不会自己退出的命令请用 start_process 在后台启动。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "要执行的命令"},
            "timeout": {"type": "integer", "description": "超时秒数，默认 60，最大 600", "default": 60},
        },
        "required": ["command"],
    }
    needs_permission = True

    def __init__(self, workspace, executor=None):
        super().__init__(workspace)
        self.executor = executor or LOCAL
        if self.executor.supports_network:  # 沙箱模式：多一个 network 参数
            self.parameters = {**self.parameters,
                               "properties": {**self.parameters["properties"], "network": NETWORK_PARAM}}

    def preview(self, command: str, timeout: int = 60, network: bool = False) -> str:
        check_dangerous(command)
        where = ("    （沙箱，联网）" if network else "    （沙箱）") if self.executor.supports_network else ""
        return f"$ {command}{where}"

    def run(self, command: str, timeout: int = 60, network: bool = False) -> str:
        check_dangerous(command)
        timeout = max(1, min(timeout, 600))
        ex = self.executor
        proc = ex.popen(command, self.ws.root, network=network)
        try:
            out, _ = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            # 只杀 shell 的话，它启动的程序还占着输出管道，communicate 会一直等下去
            ex.kill(proc)
            raise ToolError(f"命令超时（{timeout} 秒），已终止。"
                            "如果是开发服务器这类不会自己退出的进程，请用 start_process 在后台启动")
        except BaseException:  # 用户按 Ctrl+C：命令在单独的进程组里收不到，要手动终止
            ex.kill(proc)
            raise
        finally:
            ex.finished(proc)
        output = decode(out).strip()
        return f"退出码：{proc.returncode}\n{output or '(无输出)'}"
