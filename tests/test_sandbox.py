"""Docker 沙箱：安全设置、联网必须用户亲自同意；有 Docker 时再在真实容器里验证执行、断网、终止进程。"""
import time

import pytest

from coder.permissions import PermissionManager
from coder.sandbox import ENVIRONMENT, DockerSandbox, docker_status
from coder.tools import ProcessManager, ToolError, build_tools
from coder.workspace import Workspace

from test_agent import FakeLLM, SilentUI, reply, tool_call


def test_container_is_locked_down(tmp_path):
    args = DockerSandbox(tmp_path).run_args()
    joined = " ".join(args)
    for flag in ("--read-only", "--init", "--cap-drop ALL", "--security-opt no-new-privileges",
                 "--memory", "--pids-limit", "--cpus"):
        assert flag in joined
    mounts = [args[i + 1] for i, a in enumerate(args) if a == "-v"]
    assert mounts == [f"{tmp_path.resolve()}:/workspace", "coder-sandbox-home:/home/coder"]  # 只挂工作区和家目录卷
    assert "--privileged" not in args and "--network" not in args  # 启动后立刻断开默认网络


def test_network_needs_explicit_approval_even_in_auto_mode():
    asked = []

    def ask(tool, preview, **kw):
        asked.append(kw)
        return "y", ""

    pm = PermissionManager(ask=ask, auto=True)
    assert pm.check("run_command", "$ pip install x", command="pip install x") == (True, "") and asked == []
    assert pm.check("run_command", "$ pip install x", command="pip install x", network=True) == (True, "")
    assert asked == [{"network": True}]
    pm.allow_prefix("pip install")  # 白名单也不能代替联网确认
    pm.ask = lambda *a, **k: ("n", "不要联网")
    assert pm.check("run_command", "", command="pip install y", network=True) == (False, "不要联网")
    pm.ask = lambda *a, **k: ("a", "")
    pm.check("run_command", "", command="npm ci", network=True)
    assert pm.network_allowed  # 选了"本次会话允许联网"之后不再询问
    pm.ask = lambda *a, **k: pytest.fail("不应该再问")
    assert pm.check("run_command", "", command="npm ci", network=True) == (True, "")


def test_sandbox_mode_changes_tools_and_prompt(tmp_path):
    from coder.agent import Agent
    sandbox = DockerSandbox(tmp_path)
    ws = Workspace(tmp_path)
    tools = build_tools(ws, sandbox=sandbox)
    assert "network" in tools["run_command"].parameters["properties"]
    assert "network" in tools["start_process"].parameters["properties"]
    assert "network" not in build_tools(ws)["run_command"].parameters["properties"]  # 本机模式没有这个参数
    assert "（沙箱）" in tools["run_command"].preview(command="ls")
    agent = Agent(FakeLLM([]), tools, ws, PermissionManager(ask=lambda *a: ("y", "")), SilentUI(), sandbox=sandbox)
    assert ENVIRONMENT in agent.messages[0]["content"] and "cmd.exe" not in agent.messages[0]["content"]


def test_agent_forwards_network_flag(tmp_path):
    from coder.agent import Agent
    seen = []

    class Recorder(PermissionManager):
        def check(self, tool_name, preview, command=None, network=False):
            seen.append(network)
            return False, "测试里不执行"

    ws = Workspace(tmp_path)
    tools = build_tools(ws, sandbox=DockerSandbox(tmp_path))
    llm = FakeLLM([reply(calls=[tool_call("a", "run_command", command="pip install six", network=True)]),
                   reply(calls=[tool_call("b", "run_command", command="ls")]), reply("好")])
    Agent(llm, tools, ws, Recorder(ask=None), SilentUI(), sandbox=True).run("装依赖")
    assert seen == [True, False]


# ---------- 真实容器（需要 Docker 和镜像 coder-sandbox:1） ----------

READY, WHY = docker_status()
needs_docker = pytest.mark.skipif(not READY, reason=WHY)


@pytest.fixture
def sandbox(tmp_path):
    s = DockerSandbox(tmp_path)
    yield s
    s.stop()


@needs_docker
def test_commands_run_in_locked_down_container(tmp_path, sandbox):
    (tmp_path / "hello.py").write_text("print('hi from host file')\n", encoding="utf-8")
    tools = build_tools(Workspace(tmp_path), sandbox=sandbox)
    run = tools["run_command"].run
    out = run(command="id -u && python hello.py && echo made > out.txt && pwd")
    assert out.startswith("退出码：0") and "1000" in out and "hi from host file" in out and "/workspace" in out
    assert (tmp_path / "out.txt").read_text().strip() == "made"  # 写进工作区的文件在本机可见
    assert "Read-only file system" in run(command="touch /etc/x")
    assert "Could not resolve host" in run(command="curl -sS -m 5 https://pypi.org")  # 默认断网
    assert "退出码：3" in run(command="exit 3")


@needs_docker
def test_network_is_temporary(tmp_path, sandbox):
    run = build_tools(Workspace(tmp_path), sandbox=sandbox)["run_command"].run
    out = run(command="curl -sS -m 15 -o /dev/null -w '%{http_code}' https://pypi.org", network=True)
    assert out.endswith("200")
    assert "Could not resolve host" in run(command="curl -sS -m 5 https://pypi.org")  # 用完就断开


@needs_docker
def test_background_process_and_timeout_are_killed_inside_container(tmp_path, sandbox):
    processes = ProcessManager(sandbox)
    tools = build_tools(Workspace(tmp_path), processes, sandbox)
    out = tools["start_process"].run(command="echo ready; sleep 300", wait=10, wait_for="ready")
    assert "运行中" in out
    tools["stop_process"].run(id="p1")
    with pytest.raises(ToolError, match="超时"):
        tools["run_command"].run(command="sleep 300", timeout=2)
    time.sleep(0.5)
    ps = tools["run_command"].run(command="ps -eo cmd")
    assert "sleep 300" not in ps  # 容器里的进程真的被终止了，不只是本机的 docker exec 客户端


@needs_docker
def test_stop_removes_container(tmp_path):
    s = DockerSandbox(tmp_path)
    build_tools(Workspace(tmp_path), sandbox=s)["run_command"].run(command="true")
    s.stop()
    r = s._docker("container", "inspect", s.name, check=False)
    assert r.returncode != 0


@needs_docker
def test_container_removed_on_exit_even_after_objects_are_collected(tmp_path):
    """会话对象在 main() 返回后就被回收了，程序退出时仍然要删掉容器（曾经用弱引用登记，结果容器残留）。"""
    import subprocess
    import sys
    script = (
        "import gc, sys\n"
        "from coder.sandbox import DockerSandbox\n"
        "from coder.tools import build_tools\n"
        "from coder.workspace import Workspace\n"
        "def main():\n"
        f"    s = DockerSandbox(r'{tmp_path}')\n"
        f"    build_tools(Workspace(r'{tmp_path}'), sandbox=s)['run_command'].run(command='true')\n"
        "    print(s.name)\n"
        "main()\n"
        "gc.collect()\n")
    out = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=120)
    name = out.stdout.strip()
    assert name.startswith("coder-sbx-"), out.stderr
    r = DockerSandbox(tmp_path)._docker("container", "inspect", name, check=False)
    assert r.returncode != 0


def test_pid_alive():
    import subprocess
    import sys
    from coder.sandbox import pid_alive
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    assert pid_alive(__import__("os").getpid()) and not pid_alive(p.pid) and not pid_alive(0)


@needs_docker
def test_orphaned_containers_are_removed_when_a_new_sandbox_starts(tmp_path):
    """服务被直接结束（关掉终端窗口）时来不及清理；下次启动沙箱时，删掉主人已经不在的容器。"""
    import subprocess
    import sys
    from coder.sandbox import LABEL, find_docker
    docker = find_docker()
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()  # 一个已经结束的进程号
    orphan = f"coder-sbx-orphan-{p.pid}"
    subprocess.run([docker, "run", "-d", "--name", orphan, "--label", LABEL, "--label", f"coder.pid={p.pid}",
                    "coder-sandbox:1", "sleep", "infinity"], capture_output=True, check=True)
    s = DockerSandbox(tmp_path)
    try:
        build_tools(Workspace(tmp_path), sandbox=s)["run_command"].run(command="true")
        assert s._docker("container", "inspect", orphan, check=False).returncode != 0   # 孤儿被删了
        assert s._docker("container", "inspect", s.name, check=False).returncode == 0   # 自己的还在
    finally:
        s.stop()
        subprocess.run([docker, "container", "rm", "-f", orphan], capture_output=True)


@needs_docker
def test_dev_server_in_sandbox_is_previewable_from_host(tmp_path, sandbox):
    """沙箱断网，但里面启动的开发服务器能在本机浏览器打开：自动发现监听端口，经 docker exec 转发。"""
    import re
    import urllib.request
    (tmp_path / "index.html").write_text("<h1>来自沙箱</h1>" + "x" * 200_000, encoding="utf-8")  # 大响应也要完整
    processes = ProcessManager(sandbox)
    tools = build_tools(Workspace(tmp_path), processes, sandbox)
    out = tools["start_process"].run(command="python -m http.server 18080 --bind 127.0.0.1", wait=15,
                                     wait_for="Serving HTTP")
    url = re.search(r"预览地址 (http://127\.0\.0\.1:\d+)", out).group(1)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # 绕过系统代理
    for _ in range(2):  # 多个连接各自转发
        body = opener.open(url + "/index.html", timeout=20).read().decode("utf-8")
        assert body.startswith("<h1>来自沙箱</h1>") and len(body) == len("<h1>来自沙箱</h1>") + 200_000
    assert [i["port"] for i in sandbox.forwarder.items()] == [18080]
    stopped = tools["stop_process"].run(id="p1")
    assert "不再监听" in stopped and sandbox.forwarder.items() == []
