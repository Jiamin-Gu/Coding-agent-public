import pytest

from coder.tools import ToolError, build_tools
from coder.workspace import Workspace, WorkspaceError


@pytest.fixture
def tools(tmp_path):
    return build_tools(Workspace(tmp_path))


def test_sandbox_blocks_escape(tools):
    with pytest.raises(WorkspaceError):
        tools["read_file"].run(path="../outside.txt")


def test_write_then_read_with_line_numbers(tools):
    tools["write_file"].run(path="src/a.py", content="x = 1\ny = 2\n")
    out = tools["read_file"].run(path="src/a.py")
    assert "     1\tx = 1" in out and "     2\ty = 2" in out


def test_read_pagination_hint(tools):
    tools["write_file"].run(path="big.txt", content="\n".join(str(i) for i in range(100)))
    out = tools["read_file"].run(path="big.txt", offset=1, limit=10)
    assert "offset=11" in out


def test_edit_requires_unique_match(tools):
    tools["write_file"].run(path="a.py", content="x = 1\nx = 1\n")
    with pytest.raises(ToolError, match="2 次"):
        tools["edit_file"].run(path="a.py", old_string="x = 1", new_string="x = 2")
    tools["edit_file"].run(path="a.py", old_string="x = 1", new_string="x = 2", replace_all=True)
    assert "x = 1" not in tools["read_file"].run(path="a.py")


def test_edit_missing_string(tools):
    tools["write_file"].run(path="a.py", content="hello\n")
    with pytest.raises(ToolError, match="找不到"):
        tools["edit_file"].run(path="a.py", old_string="bye", new_string="hi")


def test_edit_preserves_crlf(tools, tmp_path):
    (tmp_path / "win.txt").write_bytes(b"line1\r\nline2\r\n")
    tools["read_file"].run(path="win.txt")
    tools["edit_file"].run(path="win.txt", old_string="line1\nline2", new_string="a\nb")
    assert (tmp_path / "win.txt").read_bytes() == b"a\r\nb\r\n"


def test_edit_preview_is_diff(tools):
    tools["write_file"].run(path="a.py", content="x = 1\n")
    diff = tools["edit_file"].preview(path="a.py", old_string="x = 1", new_string="x = 2")
    assert "-x = 1" in diff and "+x = 2" in diff


def test_grep(tools):
    tools["write_file"].run(path="a.py", content="def foo():\n    pass\n")
    tools["write_file"].run(path="b.txt", content="foo\n")
    assert "a.py:1:" in tools["grep"].run(pattern=r"def \w+")
    assert "b.txt" not in tools["grep"].run(pattern="foo", include="*.py")


def test_list_dir_skips_ignored(tools, tmp_path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "src").mkdir()
    out = tools["list_dir"].run()
    assert "src/" in out and "node_modules" not in out


def test_run_command(tools):
    out = tools["run_command"].run(command="echo hello")
    assert "退出码：0" in out and "hello" in out


def test_dangerous_command_blocked(tools):
    with pytest.raises(ToolError, match="安全策略"):
        tools["run_command"].preview(command="rm -rf /")


def test_read_before_edit(tools, tmp_path):
    import os
    import time
    f = tmp_path / "a.py"
    f.write_text("x = 1\n", encoding="utf-8")
    # 没读过：编辑和覆盖都被拒绝
    with pytest.raises(ToolError, match="read_file"):
        tools["edit_file"].preview(path="a.py", old_string="x = 1", new_string="x = 2")
    with pytest.raises(ToolError, match="read_file"):
        tools["write_file"].run(path="a.py", content="y = 1\n")
    # 读过之后可以改；自己改完可以继续改
    tools["read_file"].run(path="a.py")
    tools["edit_file"].run(path="a.py", old_string="x = 1", new_string="x = 2")
    tools["edit_file"].run(path="a.py", old_string="x = 2", new_string="x = 3")
    # 被外部修改后（比如用户或命令改的）需要重新读取
    time.sleep(0.01)
    f.write_text("x = 99\n", encoding="utf-8")
    os.utime(f, ns=(time.time_ns(), time.time_ns() + 1_000_000))
    with pytest.raises(ToolError, match="重新 read_file"):
        tools["edit_file"].run(path="a.py", old_string="x = 99", new_string="x = 4")
    tools["read_file"].run(path="a.py")
    tools["edit_file"].run(path="a.py", old_string="x = 99", new_string="x = 4")
