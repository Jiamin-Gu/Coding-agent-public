"""团队模式：用脚本化的假模型测试拆分、派发、文件归属、黑板推送和返工。"""
import pytest

from coder.permissions import PermissionManager
from coder.team import LEAD, Blackboard, Team
from coder.tools import ToolError

import time

from test_agent import FakeLLM, SilentUI, reply, tool_call


class SubLLM(FakeLLM):
    """子 agent 的假模型：第一次调用前稍等一下，保证主 agent 派发后先拿到"已派出"、再等汇报（测试结果稳定）。"""

    def __init__(self, replies, delay=0.05):
        super().__init__(replies)
        self.delay, self.started, self.tools_seen = delay, None, []

    def chat(self, messages, tools, on_delta=None):
        self.tools_seen.append(tools or [])
        if self.started is None:
            self.started = time.monotonic()
            time.sleep(self.delay)
        return super().chat(messages, tools, on_delta)


def done(summary, verification="已运行相关测试，通过"):
    """子 agent 交付。"""
    return reply(calls=[tool_call("ct", "complete_task", summary=summary, verification=verification)])


def delivered(message, text):
    """这条助手消息里有没有用 complete_task 交付这段文字（参数是 JSON，中文被转义了，解开再比）。"""
    import json
    return any(text in json.loads(c["function"]["arguments"]).get("summary", "")
               for c in message.get("tool_calls") or [] if c["function"]["name"] == "complete_task")


WAIT = reply("等它们完成")  # 主 agent 没事可做：结束这一步，系统等下一个子 agent 的汇报


def saw(llm, text):
    """这个 agent 收到过的消息里有没有这段文字。"""
    return any(text in str(m.get("content")) for msgs in llm.seen for m in msgs)


def make_team(tmp_path, scripts: list[list]):
    """scripts 按创建顺序分给各个 agent：第一个是主 agent，之后是按派发顺序创建的子 agent。"""
    llms = [FakeLLM(scripts[0])] + [SubLLM(s) for s in scripts[1:]]
    queue = list(llms)
    team = Team(lambda: queue.pop(0), tmp_path, PermissionManager(ask=lambda *a: ("y", ""), auto=True),
                SilentUI(), max_steps=10, quality_roles=False)
    return team, llms


PLAN = dict(tasks=[{"id": "core", "role": "backend", "description": "实现 add", "files": ["pkg/core.py"]},
                   {"id": "cli", "role": "backend", "description": "实现命令行", "files": ["pkg/cli.py"], "depends": ["core"]}],
            contracts=[{"name": "add", "text": "add(a: int, b: int) -> int"}])


def test_plan_dispatch_and_ownership(tmp_path):
    lead = [reply(calls=[tool_call("p", "plan_tasks", **PLAN)]),
            reply(calls=[tool_call("d1", "dispatch", task_ids=["core"])]), WAIT,
            reply(calls=[tool_call("d2", "dispatch", task_ids=["cli"])]), WAIT,
            reply("全部完成")]
    core = [reply(calls=[tool_call("w", "write_file", path="pkg/core.py", content="def add(a, b):\n    return a + b\n")]),
            reply(calls=[tool_call("x", "write_file", path="pkg/cli.py", content="越权")]),
            reply(calls=[tool_call("b", "board_post", kind="decision", text="add 不做类型检查")]),
            done("core 完成")]
    cli = [reply(calls=[tool_call("w", "write_file", path="pkg/cli.py", content="from pkg.core import add\n")]),
           done("cli 完成")]
    team, llms = make_team(tmp_path, [lead, core, cli])
    team.run("做一个加法工具")

    assert (tmp_path / "pkg/core.py").is_file() and (tmp_path / "pkg/cli.py").read_text() == "from pkg.core import add\n"
    # 写别人的文件被拒绝，错误信息指出归属
    denied = [m["content"] for m in team.subagents["core"].messages if m["role"] == "tool"][1]
    assert denied.startswith("错误") and "cli" in denied
    # 子 agent 的任务说明里带着契约
    assert "add(a: int, b: int) -> int" in llms[1].seen[0][1]["content"]
    # dispatch 马上返回，不等子 agent 做完
    assert "已派出：core" in llms[0].seen[2][-1]["content"]
    # core 的决策：写进后派出的 cli 的任务说明，也推给主 agent
    assert "add 不做类型检查" in llms[2].seen[0][1]["content"]
    assert saw(llms[0], "add 不做类型检查")
    # 主 agent 拿到汇报（complete_task 交付的内容）
    assert saw(llms[0], "core 完成") and saw(llms[0], "验证：已运行相关测试")
    assert team.board.tasks["core"]["status"] == "done" and team.board.tasks["cli"]["status"] == "done"
    # 操作日志按时间顺序记录了成功的写入（越权的那次没有记录）
    assert [o["args"]["path"] for o in team.ops] == ["pkg/core.py", "pkg/cli.py"]
    assert team.steps == 6 + 4 + 2 and team.usage["prompt"] == 0


def test_dependencies_and_rework_keep_context(tmp_path):
    lead = [reply(calls=[tool_call("p", "plan_tasks", **PLAN)]),
            reply(calls=[tool_call("d", "dispatch", task_ids=["cli"])]),  # 依赖还没完成
            reply(calls=[tool_call("d1", "dispatch", task_ids=["core"])]), WAIT,
            reply(calls=[tool_call("d2", "dispatch", task_ids=["core"], feedback="test_add 失败：期望 3")]), WAIT,
            reply("完成")]
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg/core.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    core = [done("第一次完成"), done("修好了")]
    team, llms = make_team(tmp_path, [lead, core])
    team.run("x")
    assert "依赖的任务还没完成" in llms[0].seen[2][-1]["content"]
    # 返工沿用同一个子 agent，上下文里有第一次的内容和返工意见
    second = llms[1].seen[1]
    assert any(delivered(m, "第一次完成") for m in second)
    assert "test_add 失败" in second[-1]["content"]
    assert len(team.subagents) == 1


def test_plan_rejects_overlapping_files(tmp_path):
    team, _ = make_team(tmp_path, [[]])
    with pytest.raises(ToolError, match="重叠"):
        team.plan([{"id": "a", "role": "backend", "description": "", "files": ["pkg/*.py"]},
                   {"id": "b", "role": "backend", "description": "", "files": ["pkg/x.py"]}], [])
    with pytest.raises(ToolError, match="不存在"):
        team.plan([{"id": "a", "role": "backend", "description": "", "files": ["a.py"], "depends": ["zzz"]}], [])


def test_blackboard_contract_single_writer_and_digest():
    board = Blackboard()
    board.set_contract(LEAD, "api", "f(x)")
    board.set_contract("core", "fmt", "JSON")
    with pytest.raises(ToolError, match="只有它能修改"):
        board.set_contract("cli", "fmt", "CSV")
    with pytest.raises(ToolError):
        board.set_contract("cli", "api", "g(x)")
    board.set_contract(LEAD, "fmt", "JSON v2")  # lead 可以改任何契约
    assert board.contracts["fmt"] == {"owner": "core", "text": "JSON v2"}
    board.post("core", "question", "要不要分页？", to=LEAD)
    text, version = board.digest("cli", 0)
    assert "要不要分页" not in text and "JSON v2" in text  # 发给 lead 的提问不推给 cli
    text, _ = board.digest(LEAD, 0)
    assert "要不要分页" in text
    assert board.digest("cli", version) == ("", version)  # 已经推送过的不再重复


def test_permissions_shared_across_team(tmp_path):
    asked = []
    base = PermissionManager(ask=lambda n, p: (asked.append(n), ("a", ""))[1], auto=False)
    team = Team(lambda: FakeLLM([]), tmp_path, base, SilentUI())
    lead_perms = team.lead.permissions
    assert lead_perms.check("write_file", "x") == (True, "") and asked == ["write_file"]
    assert base.always_allowed == {"write_file"}  # 在团队里选"总是允许"，写回共享设置
    assert lead_perms.check("write_file", "y") == (True, "") and len(asked) == 1
    base.auto = True  # 界面上切换自动模式，团队里立即生效
    assert lead_perms.check("run_command", "z") == (True, "") and len(asked) == 1


def test_full_request_and_context_files_are_handed_to_sub_agent(tmp_path):
    """按任务分配上下文：完整的原始要求、主 agent 指定的文件内容一开始就交给子 agent，并记为已读。"""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "SPEC.md").write_text("## 规则\n金额保留两位小数", encoding="utf-8")
    (tmp_path / "core.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    long_request = "实现规格里的功能。" + "细节" * 3000  # 超过以前 2000 字的截断
    plan = {"tasks": [{"id": "core", "role": "backend", "description": "修好 add", "files": ["core.py"],
                       "context": ["docs/SPEC.md", "core.py", "missing.py"]}]}
    lead = [reply(calls=[tool_call("p", "plan_tasks", **plan)]),
            reply(calls=[tool_call("d", "dispatch", task_ids=["core"])]), WAIT, reply("完成")]
    # 子 agent 第一步就直接修改 core.py：文件已经交给它并记为已读，不需要先 read_file
    core = [reply(calls=[tool_call("e", "edit_file", path="core.py", old_string="a - b", new_string="a + b")]),
            done("修好了")]
    team, llms = make_team(tmp_path, [lead, core])
    team.run(long_request)
    first = llms[1].seen[0][1]["content"]
    assert long_request in first
    assert "金额保留两位小数" in first and "return a - b" in first and "missing.py" in first
    assert (tmp_path / "core.py").read_text(encoding="utf-8") == "def add(a, b):\n    return a + b\n"
    edit_result = [m for m in team.subagents["core"].messages if m["role"] == "tool"][0]["content"]
    assert not edit_result.startswith("错误")


def test_roles_validation_and_read_only_security(tmp_path):
    team, _ = make_team(tmp_path, [[], []])
    with pytest.raises(ToolError, match="role"):
        team.plan([{"id": "a", "description": "", "files": ["a.py"]}], [])  # 没写岗位
    with pytest.raises(ToolError, match="role"):
        team.plan([{"id": "a", "role": "manager", "description": "", "files": ["a.py"]}], [])
    with pytest.raises(ToolError, match="最多"):
        team.plan([{"id": f"t{i}", "role": "tester", "description": "", "files": [f"t{i}.py"]} for i in range(4)], [])
    team.plan([{"id": "sec", "role": "security", "description": "审查", "files": ["a.py"]}], [])
    assert team.board.tasks["sec"]["files"] == []  # 安全审查不负责任何文件
    agent = team._make_agent("sec", [], 5, SilentUI())
    with pytest.raises(ToolError, match="不归你负责"):
        agent.tools["write_file"].run(path="a.py", content="x")


def test_sub_agent_gets_role_duty(tmp_path):
    plan = {"tasks": [{"id": "ui", "role": "frontend", "description": "做页面", "files": ["index.html"]}]}
    lead = [reply(calls=[tool_call("p", "plan_tasks", **plan)]),
            reply(calls=[tool_call("d", "dispatch", task_ids=["ui"])]), WAIT, reply("完成")]
    ui = [reply(calls=[tool_call("w", "write_file", path="index.html", content="<h1>hi</h1>")]), done("页面做好了")]
    team, llms = make_team(tmp_path, [lead, ui])
    team.run("做个页面")
    first = llms[1].seen[0][1]["content"]
    assert "# Your role: frontend（前端）" in first and "escape any data you render" in first


def test_quality_roles_always_run_in_team_mode(tmp_path):
    """主 agent 自己写完代码就想结束：团队模式要求测试和安全审查都出场，提醒它补上。"""
    plan = {"tasks": [
        {"id": "qa", "role": "tester", "description": "写测试并运行", "files": ["test_add.py"]},
        {"id": "sec", "role": "security", "description": "审查 add.py", "files": []}]}
    lead = [reply(calls=[tool_call("w", "write_file", path="add.py", content="def add(a, b):\n    return a + b\n")]),
            reply("写完了"),
            # 被提醒后补上测试和安全审查
            reply(calls=[tool_call("p", "plan_tasks", **plan)]),
            reply(calls=[tool_call("d", "dispatch", task_ids=["qa"])]), WAIT,
            reply(calls=[tool_call("d2", "dispatch", task_ids=["sec"])]), WAIT,
            reply("测试通过，没有安全问题")]
    qa = [reply(calls=[tool_call("w", "write_file", path="test_add.py", content="def test_add():\n    pass\n")]),
          done("测试都通过")]
    queue = [FakeLLM(lead), SubLLM(qa), SubLLM([done("未发现安全问题", "只读审查，不需要运行")])]
    llms = list(queue)
    team = Team(lambda: queue.pop(0), tmp_path, PermissionManager(ask=lambda *a: ("y", ""), auto=True),
                SilentUI(), max_steps=10)
    team.run("写一个 add 函数")
    reminder = [m for m in team.lead.messages if m["role"] == "user" and "quality roles" in str(m["content"])]
    assert len(reminder) == 1 and "tester" in reminder[0]["content"] and "security" in reminder[0]["content"]
    assert {t["role"]: t["status"] for t in team.board.tasks.values()} == {"tester": "done", "security": "done"}
    assert team.missing_quality_roles() == [] and saw(llms[0], "未发现安全问题")


def test_no_reminder_when_nothing_was_written(tmp_path):
    team, llms = make_team(tmp_path, [[reply("这个问题不需要改代码，答案是 42")]])
    team.quality_roles = True
    team.run("解释一下")
    assert len(llms[0].seen) == 1  # 没写代码：不需要测试和安全审查


def test_export_and_restore_resumes_interrupted_sub_agent(tmp_path):
    """服务重启：黑板、子 agent 的对话恢复；正在进行的任务标记为被打断，重新派发时子 agent 接着之前的进度做。"""
    lead = [reply(calls=[tool_call("p", "plan_tasks", **PLAN)]),
            reply(calls=[tool_call("d1", "dispatch", task_ids=["core"])]), WAIT, reply("先到这里")]
    core = [reply(calls=[tool_call("w", "write_file", path="pkg/core.py", content="def add(a, b):\n    return a + b\n")]),
            done("core 第一阶段完成")]
    team, _ = make_team(tmp_path, [lead, core])
    team.run("做一个加法工具")
    # 模拟服务在 core 工作到一半时被关掉：状态停在 running，对话停在一个还没有结果的工具调用上
    team.board.tasks["core"]["status"] = "running"
    team.subagents["core"].messages.append({"role": "assistant", "content": "", "tool_calls": [
        {"id": "x", "type": "function", "function": {"name": "read_file", "arguments": '{"path": "pkg/core.py"}'}}]})
    state = team.export_state()

    lead2 = [reply(calls=[tool_call("d2", "dispatch", task_ids=["core"])]), WAIT, reply("都做完了")]
    core2 = [done("接着做完了")]
    team2, llms = make_team(tmp_path, [lead2, core2])
    interrupted = team2.restore_state(state)
    assert interrupted == ["core"] and team2.board.tasks["core"]["status"] == "interrupted"
    assert team2.board.contracts["add"]["text"] == "add(a: int, b: int) -> int"
    sub = team2.subagents["core"]
    assert any(delivered(m, "core 第一阶段完成") for m in sub.messages)  # 对话恢复了
    assert sub.messages[-1]["role"] == "tool"                                # 中断的工具调用补上了结果
    team2.run("继续")
    assert "service restarted" in llms[0].seen[0][-1]["content"] and "core" in llms[0].seen[0][-1]["content"]
    assert "Continue where you left off" in llms[1].seen[0][-1]["content"]   # 子 agent 收到的是"接着做"
    assert team2.board.tasks["core"]["status"] == "done"


def test_quality_roles_have_smaller_step_limits(tmp_path):
    """安全审查和测试岗位的步数上限比实现任务小（实测它们最容易在反复试验上花掉大量步数）。"""
    team, _ = make_team(tmp_path, [[]])
    team.plan([{"id": "impl", "role": "backend", "description": "", "files": ["a.py"]},
               {"id": "qa", "role": "tester", "description": "", "files": ["tests/acceptance/test_a.py"]},
               {"id": "sec", "role": "security", "description": "", "files": []}], [])
    assert team._steps_for("impl") == team.sub_max_steps
    assert team._steps_for("qa") == 30 and team._steps_for("sec") == 20
    team.sub_max_steps = 10  # 团队的上限更小时取较小的
    assert team._steps_for("sec") == 10


# ---------------------------------------------------------------- 新流程

def test_dispatch_does_not_block_dependents_wait_only_for_their_dependency(tmp_path):
    """派发不阻塞：core 先做完，依赖它的 cli 马上派出，不用等同时在跑、还很慢的 docs。"""
    plan = {"tasks": PLAN["tasks"] + [{"id": "docs", "role": "docs", "description": "写文档", "files": ["README.md"]}]}
    lead = [reply(calls=[tool_call("p", "plan_tasks", **plan)]),
            reply(calls=[tool_call("d1", "dispatch", task_ids=["core", "docs"])]), WAIT,   # 先回来的是 core
            reply(calls=[tool_call("d2", "dispatch", task_ids=["cli"])]), WAIT, WAIT, reply("都好了")]
    core = [reply(calls=[tool_call("w", "write_file", path="pkg/core.py", content="def add(a, b):\n    return a + b\n")]),
            done("core 完成")]
    docs = [reply(calls=[tool_call("w", "write_file", path="README.md", content="# 加法工具")]), done("文档写好了")]
    cli = [reply(calls=[tool_call("w", "write_file", path="pkg/cli.py", content="from pkg.core import add\n")]),
           done("cli 完成")]
    llms = [FakeLLM(lead), SubLLM(core), SubLLM(docs, delay=0.8), SubLLM(cli)]
    queue = list(llms)
    team = Team(lambda: queue.pop(0), tmp_path, PermissionManager(ask=lambda *a: ("y", ""), auto=True),
                SilentUI(), max_steps=10, quality_roles=False)
    team.run("做一个加法工具")
    assert {t: v["status"] for t, v in team.board.tasks.items()} == {"core": "done", "cli": "done", "docs": "done"}
    docs_done = next(i for i, msgs in enumerate(llms[0].seen) if any("文档写好了" in str(m.get("content")) for m in msgs))
    cli_sent = next(i for i, msgs in enumerate(llms[0].seen) if any("已派出：cli" in str(m.get("content")) for m in msgs))
    assert cli_sent < docs_done                          # cli 在 docs 交回之前就派出了
    assert llms[3].started < llms[2].started + 0.8       # cli 开工时 docs 还在跑


def test_complete_task_checks_the_delivery(tmp_path):
    """子 agent 交付时的机械检查：负责的文件不存在、Python 语法错误、改了代码没验证，都退回给它自己改。"""
    plan = {"tasks": [{"id": "core", "role": "backend", "description": "实现 add", "files": ["pkg/core.py"]}]}
    lead = [reply(calls=[tool_call("p", "plan_tasks", **plan)]),
            reply(calls=[tool_call("d", "dispatch", task_ids=["core"])]), WAIT, reply("完成")]
    core = [done("做完了", ""),                                                     # 文件还不存在
            reply(calls=[tool_call("w", "write_file", path="pkg/core.py", content="def add(a, b)\n    return a + b\n")]),
            done("做完了", ""),                                                     # 语法错误、没验证
            reply(calls=[tool_call("w2", "write_file", path="pkg/core.py", content="def add(a, b):\n    return a + b\n")]),
            done("修好了", "python -c 'import pkg.core' 通过")]
    team, llms = make_team(tmp_path, [lead, core])
    team.run("x")
    results = [m["content"] for m in team.subagents["core"].messages if m["role"] == "tool"]
    assert "不存在" in results[0] and results[0].startswith("错误：交付检查没通过")
    assert "语法错误" in results[2] and "没有成功运行过验证" in results[2]
    assert results[-1].startswith("已交付") and team.board.tasks["core"]["status"] == "done"


def test_delivery_accepted_after_too_many_rejections_with_problems_reported(tmp_path):
    plan = {"tasks": [{"id": "core", "role": "backend", "description": "实现 add", "files": ["pkg/core.py"]}]}
    lead = [reply(calls=[tool_call("p", "plan_tasks", **plan)]),
            reply(calls=[tool_call("d", "dispatch", task_ids=["core"])]), WAIT, reply("完成")]
    team, llms = make_team(tmp_path, [lead, [done("做完了")] * 3])
    team.run("x")
    assert team.board.tasks["core"]["status"] == "done"
    assert saw(llms[0], "交付检查没通过：你负责的文件 pkg/core.py 不存在")   # 带着问题交给主 agent


def test_sub_agent_must_deliver_with_complete_task(tmp_path):
    """纯文字回复不算交付：提醒两次还不交付，任务算未完成；步数用完时给一次只能交付的收尾回合。"""
    plan = {"tasks": [{"id": "sec", "role": "security", "description": "审查", "files": []}]}
    lead = [reply(calls=[tool_call("p", "plan_tasks", **plan)]),
            reply(calls=[tool_call("d", "dispatch", task_ids=["sec"])]), WAIT, reply("完成")]
    team, llms = make_team(tmp_path, [lead, [reply("没问题"), reply("真的没问题"), reply("我说完了")]])
    team.run("x")
    assert team.board.tasks["sec"]["status"] == "unfinished"
    assert sum("还没有调用 complete_task" in str(m.get("content")) for m in team.subagents["sec"].messages) == 2

    lead = [reply(calls=[tool_call("p", "plan_tasks", **plan)]),
            reply(calls=[tool_call("d", "dispatch", task_ids=["sec"])]), WAIT, reply("完成")]
    looping = [reply(calls=[tool_call(f"l{i}", "list_dir", path=".")]) for i in range(3)]
    (tmp_path / "b").mkdir()
    team, llms = make_team(tmp_path / "b", [lead, looping + [done("看完了，没问题", "只读")]])
    team.sub_max_steps = 3
    team.run("x")
    sub = team.subagents["sec"]
    assert team.board.tasks["sec"]["status"] == "done"
    assert "最后一次机会" in str(llms[1].seen[-1][-1]["content"])
    assert [t["function"]["name"] for t in llms[1].tools_seen[-1]] == ["complete_task"]   # 收尾回合只能交付
    assert sub.finished


def test_lead_cannot_edit_files_of_a_running_task(tmp_path):
    plan = {"tasks": [{"id": "core", "role": "backend", "description": "实现 add", "files": ["pkg/core.py"]}]}
    lead = [reply(calls=[tool_call("p", "plan_tasks", **plan)]),
            reply(calls=[tool_call("d", "dispatch", task_ids=["core"])]),
            reply(calls=[tool_call("w", "write_file", path="pkg/core.py", content="主 agent 抢着改")]), WAIT, reply("完成")]
    core = [reply(calls=[tool_call("w", "write_file", path="pkg/core.py", content="def add(a, b):\n    return a + b\n")]),
            done("core 完成")]
    llms = [FakeLLM(lead), SubLLM(core, delay=0.3)]
    queue = list(llms)
    team = Team(lambda: queue.pop(0), tmp_path, PermissionManager(ask=lambda *a: ("y", ""), auto=True),
                SilentUI(), max_steps=10, quality_roles=False)
    team.run("x")
    refused = [m["content"] for m in team.lead.messages if m["role"] == "tool"][2]
    assert refused.startswith("错误") and "正在运行的任务 core" in refused
    assert (tmp_path / "pkg/core.py").read_text(encoding="utf-8").startswith("def add")


def test_rework_that_changes_files_notifies_dependents(tmp_path):
    """返工改了文件：依赖它、已经完成的任务和主 agent 都收到通知。"""
    lead = [reply(calls=[tool_call("p", "plan_tasks", **PLAN)]),
            reply(calls=[tool_call("d1", "dispatch", task_ids=["core"])]), WAIT,
            reply(calls=[tool_call("d2", "dispatch", task_ids=["cli"])]), WAIT,
            reply(calls=[tool_call("d3", "dispatch", task_ids=["core"], feedback="add 要支持小数")]), WAIT,
            reply("完成")]
    core = [reply(calls=[tool_call("w", "write_file", path="pkg/core.py", content="def add(a, b):\n    return a + b\n")]),
            done("core 完成"),
            reply(calls=[tool_call("w2", "write_file", path="pkg/core.py", content="def add(a, b):\n    return float(a) + b\n")]),
            done("支持小数了")]
    cli = [reply(calls=[tool_call("w", "write_file", path="pkg/cli.py", content="from pkg.core import add\n")]),
           done("cli 完成")]
    team, llms = make_team(tmp_path, [lead, core, cli])
    team.run("x")
    assert saw(llms[0], "core 返工改了 pkg/core.py；依赖它、已经完成的任务：cli")
    assert "你依赖的 core 返工改了 pkg/core.py" in team.board.notes_for("cli")


def test_user_can_steer_the_lead_while_the_team_runs(tmp_path):
    plan = {"tasks": [{"id": "core", "role": "backend", "description": "实现 add", "files": ["pkg/core.py"]}]}
    lead = [reply(calls=[tool_call("p", "plan_tasks", **plan)]),
            reply(calls=[tool_call("d", "dispatch", task_ids=["core"])]), WAIT, reply("完成")]
    core = [reply(calls=[tool_call("w", "write_file", path="pkg/core.py", content="def add(a, b):\n    return a + b\n")]),
            done("core 完成")]
    team, llms = make_team(tmp_path, [lead, core])
    team.steer("记得写类型注解")
    team.run("x")
    assert saw(llms[0], "[用户在你工作时补充：]") and saw(llms[0], "记得写类型注解")


def test_queued_tasks_do_not_start_after_a_stop(tmp_path):
    """超过并行上限、还在排队的子任务：这一轮被停止后不再开始（开始运行时会清掉停止标志，所以要提前检查）。"""
    team, llms = make_team(tmp_path, [[], [done("不该运行")]])
    team.plan([{"id": "core", "role": "backend", "description": "", "files": ["core.py"]}], [])
    team.subagents["core"] = team._make_agent("core", ["core.py"], 5, SilentUI())
    team._abort = True
    team._run_in_background("core", "")
    assert team.board.tasks["core"]["status"] == "cancelled" and llms[1].seen == []


def test_steering_reaches_the_lead_while_it_waits_for_sub_agents(tmp_path):
    """主 agent 在等子 agent 汇报时，用户的插话马上送到，不用等子 agent 做完。"""
    import threading
    plan = {"tasks": [{"id": "core", "role": "backend", "description": "实现 add", "files": ["pkg/core.py"]}]}
    lead = [reply(calls=[tool_call("p", "plan_tasks", **plan)]),
            reply(calls=[tool_call("d", "dispatch", task_ids=["core"])]), WAIT,
            reply("收到补充，继续等"), reply("完成")]
    core = [reply(calls=[tool_call("w", "write_file", path="pkg/core.py", content="def add(a, b):\n    return a + b\n")]),
            done("core 完成")]
    llms = [FakeLLM(lead), SubLLM(core, delay=0.6)]
    queue = list(llms)
    team = Team(lambda: queue.pop(0), tmp_path, PermissionManager(ask=lambda *a: ("y", ""), auto=True),
                SilentUI(), max_steps=10, quality_roles=False)
    threading.Timer(0.2, lambda: team.steer("记得写类型注解")).start()
    team.run("x")
    seen = [str(msgs[-1].get("content")) for msgs in llms[0].seen]
    steer_at = next(i for i, c in enumerate(seen) if "记得写类型注解" in c)
    report_at = next(i for i, c in enumerate(seen) if "core 完成" in c)
    assert steer_at < report_at
