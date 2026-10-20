"""后台进程：启动、增量读取输出、等待指定内容、连同子进程一起终止、会话结束时清理。"""
import os
import sys
import time
from pathlib import Path

import pytest

from coder.tools import ProcessManager, ToolError, build_tools
from coder.tools.process import decode_partial
from coder.workspace import Workspace

PY = f'"{sys.executable}"'


def make(tmp_path):
    manager = ProcessManager()
    return build_tools(Workspace(tmp_path), manager), manager


def test_start_read_and_stop(tmp_path):
    (tmp_path / "srv.py").write_text(
        "import time\nprint('Listening on 8000', flush=True)\n"
        "i = 0\nwhile True:\n    i += 1\n    print('tick', i, flush=True)\n    time.sleep(0.2)\n", encoding="utf-8")
    tools, manager = make(tmp_path)
    try:
        out = tools["start_process"].run(command=f"{PY} srv.py", wait=10, wait_for="Listening")
        assert out.startswith("进程 p1：运行中") and "Listening on 8000" in out
        time.sleep(0.8)
        more = tools["process_output"].run(id="p1")
        assert "tick" in more and "Listening" not in more  # 只返回新输出
        assert "p1 [运行中]" in tools["list_processes"].run()
        stopped = tools["stop_process"].run(id="p1")
        assert "已退出" in stopped and manager.running() == []
    finally:
        manager.stop_all()


def test_process_that_exits_and_unknown_id(tmp_path):
    tools, manager = make(tmp_path)
    out = tools["start_process"].run(command=f"{PY} -c \"print('done')\"", wait=10)
    assert "已退出（退出码 0）" in out and "done" in out  # 自己结束的进程不用等满时间
    with pytest.raises(ToolError, match="没有后台进程"):
        tools["process_output"].run(id="p9")


def test_stop_kills_child_processes(tmp_path):
    """shell 启动的 python 再启动一个孙进程：停止时整棵进程树都要终止。"""
    (tmp_path / "child.py").write_text("import time\nwhile True:\n    time.sleep(0.1)\n", encoding="utf-8")
    (tmp_path / "parent.py").write_text(
        "import subprocess, sys, time\n"
        f"p = subprocess.Popen([sys.executable, 'child.py'])\nprint(p.pid, flush=True)\n"
        "while True:\n    time.sleep(0.1)\n", encoding="utf-8")
    tools, manager = make(tmp_path)
    out = tools["start_process"].run(command=f"{PY} parent.py", wait=10, wait_for=r"^\d+")
    child_pid = int(out.split("--- 输出 ---\n")[1].split()[0])
    manager.stop_all()
    time.sleep(0.5)
    assert not _alive(child_pid)


def _alive(pid: int) -> bool:
    import os
    import subprocess
    if os.name == "nt":
        r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True)
        return str(pid) in r.stdout
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def test_run_command_timeout_kills_tree_and_returns(tmp_path):
    tools, _ = make(tmp_path)
    start = time.time()
    with pytest.raises(ToolError, match="start_process"):
        tools["run_command"].run(command=f"{PY} -c \"import time; time.sleep(30)\"", timeout=1)
    assert time.time() - start < 15  # 以前子进程占着管道，会一直等到它自己结束


def test_dangerous_and_limits(tmp_path, monkeypatch):
    tools, manager = make(tmp_path)
    with pytest.raises(ToolError, match="安全策略"):
        tools["start_process"].preview(command="rm -rf /")
    monkeypatch.setattr("coder.tools.process.MAX_RUNNING", 1)
    try:
        tools["start_process"].run(command=f"{PY} -c \"import time; time.sleep(30)\"", wait=0)
        with pytest.raises(ToolError, match="上限"):
            tools["start_process"].run(command="echo x", wait=0)
    finally:
        manager.stop_all()


def test_decode_partial_keeps_split_utf8_for_next_read():
    data = "你好".encode("utf-8")
    text, used = decode_partial(data[:4])  # "你" 完整，"好" 只到一半
    assert text == "你" and used == 3


def test_processes_killed_on_exit_even_after_objects_are_collected(tmp_path):
    import subprocess
    """会话对象在 main() 返回后就被回收了，程序退出时仍然要终止后台进程（曾经用弱引用登记，结果进程残留）。"""
    import subprocess
    (tmp_path / "child.py").write_text("import time\nwhile True:\n    time.sleep(0.1)\n", encoding="utf-8")
    (tmp_path / "parent.py").write_text(
        "import subprocess, sys\np = subprocess.Popen([sys.executable, 'child.py'])\nprint(p.pid, flush=True)\np.wait()\n",
        encoding="utf-8")
    (tmp_path / "driver.py").write_text(
        "import gc, sys\n"
        "from coder.tools import build_tools\n"
        "from coder.workspace import Workspace\n"
        "def main():\n"
        "    tools = build_tools(Workspace(sys.argv[1]))\n"
        "    out = tools['start_process'].run(command=f'\"{sys.executable}\" parent.py', wait=10, wait_for=r'\\d+')\n"
        "    print(out.split('--- 输出 ---')[1].split()[0])\n"
        "main()\n"
        "gc.collect()\n", encoding="utf-8")
    # 脚本在临时目录里，Python 只从脚本所在的目录找模块：要显式告诉它项目在哪（本机全局装过 coder 时碰巧能找到，CI 上找不到）
    root = Path(__file__).resolve().parent.parent
    env = {**os.environ, "PYTHONPATH": str(root) + os.pathsep + os.environ.get("PYTHONPATH", "")}
    out = subprocess.run([sys.executable, str(tmp_path / "driver.py"), str(tmp_path)], capture_output=True,
                         text=True, encoding="utf-8", timeout=60, cwd=root, env=env)
    assert out.stdout.strip(), f"驱动脚本没有输出：{out.stderr[-2000:]}"
    child = int(out.stdout.strip().splitlines()[-1])
    time.sleep(0.5)
    assert not _alive(child), out.stderr
