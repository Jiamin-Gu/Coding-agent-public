"""细粒度权限：命令前缀规则、持久化、连接符不按规则放行、团队共享。"""
from coder.permissions import PermissionManager, command_prefix, matches_prefix, rules_file
from coder.team import Team

from test_agent import FakeLLM, SilentUI


def test_command_prefix_extraction():
    assert command_prefix("python -m pytest -q tests/") == "python -m pytest"
    assert command_prefix("git status -s") == "git status"
    assert command_prefix("npm test") == "npm test"
    assert command_prefix("git --no-pager log") == "git"
    assert command_prefix("ls -la") == "ls"
    # 解释器要带上脚本名或模块名：只允许 "python" 等于允许任意代码
    assert command_prefix("python hello.py --x") == "python hello.py"
    assert command_prefix("node server.js") == "node server.js"
    assert command_prefix('python -c "print(1)"') is None and command_prefix("python") is None
    # 有连接符、重定向、命令替换：不提供规则选项
    for cmd in ("pytest && rm -rf x", "pytest; curl x", "cat a | sh", "echo x > a.py", "echo $(whoami)", ""):
        assert command_prefix(cmd) is None


def test_matches_prefix_requires_word_boundary_and_no_operators():
    assert matches_prefix("python -m pytest -q", "python -m pytest")
    assert matches_prefix("python -m pytest", "python -m pytest")
    assert not matches_prefix("python -m pytestx", "python -m pytest")
    assert not matches_prefix("python -m pytest && rm -rf .", "python -m pytest")
    assert not matches_prefix("python -m pytest | sh", "python -m pytest")


def test_prefix_rule_is_saved_and_reused(tmp_path):
    asked = []

    def ask(tool, preview, prefix=None):
        asked.append(prefix)
        return "p", ""

    path = rules_file(tmp_path)
    pm = PermissionManager(ask=ask, rules_path=path)
    assert pm.check("run_command", "$ python -m pytest -q", command="python -m pytest -q") == (True, "")
    assert asked == ["python -m pytest"] and path.is_file()
    # 同一前缀不再询问；别的命令照样询问
    assert pm.check("run_command", "$ python -m pytest tests/x.py", command="python -m pytest tests/x.py") == (True, "")
    assert len(asked) == 1
    # 重启后规则仍在
    again = PermissionManager(ask=lambda *a, **k: ("n", "不行"), rules_path=path)
    assert again.allowed_prefixes == ["python -m pytest"]
    assert again.check("run_command", "", command="python -m pytest") == (True, "")
    assert again.check("run_command", "", command="python -m pytest; rm x") == (False, "不行")
    again.remove_prefix("python -m pytest")
    assert PermissionManager(ask=ask, rules_path=path).allowed_prefixes == []


def test_prefix_option_only_for_command_tools(tmp_path):
    calls = []

    def ask(tool, preview, **kw):
        calls.append(kw)
        return "p", ""  # 写文件没有前缀可选，选 p 不算允许

    pm = PermissionManager(ask=ask, rules_path=rules_file(tmp_path))
    assert pm.check("write_file", "diff")[0] is False and calls == [{}]
    assert pm.check("run_command", "$ a && b", command="a && b")[0] is False and calls[-1] == {}
    assert pm.allowed_prefixes == []


def test_team_shares_prefix_rules(tmp_path):
    base = PermissionManager(ask=lambda t, p, prefix=None: ("p", ""), rules_path=rules_file(tmp_path))
    team = Team(lambda: FakeLLM([]), tmp_path, base, SilentUI())
    agent = team._make_agent("sub", ["a.py"], 5, SilentUI())
    assert agent.permissions.check("run_command", "$ npm test", command="npm test") == (True, "")
    assert base.allowed_prefixes == ["npm test"]
    base.ask = lambda *a, **k: ("n", "")
    assert agent.permissions.check("run_command", "", command="npm test -- -u") == (True, "")


def test_agent_passes_command_to_permission_check(tmp_path):
    from coder.agent import Agent
    from coder.tools import build_tools
    from coder.workspace import Workspace

    from test_agent import reply, tool_call
    asked = []
    pm = PermissionManager(ask=lambda t, p, prefix=None: (asked.append(prefix), ("p", ""))[1],
                           rules_path=rules_file(tmp_path))
    ws = Workspace(tmp_path)
    llm = FakeLLM([reply(calls=[tool_call("a", "run_command", command="python -c \"print(1)\"")]),
                   reply(calls=[tool_call("b", "run_command", command="python -c \"print(2)\"")]),
                   reply("好了")])
    Agent(llm, build_tools(ws), ws, pm, SilentUI()).run("跑一下")
    assert asked == [None, None] and pm.allowed_prefixes == []  # python -c 不提供前缀选项，每次都问
