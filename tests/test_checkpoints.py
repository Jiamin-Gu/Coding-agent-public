"""检查点和撤销：恢复修改、删除新建、检测之后的手动修改、告诉模型、团队模式一起撤销。"""
from coder.checkpoints import Checkpoints, describe
from coder.permissions import PermissionManager
from coder.team import Team

from test_agent import FakeLLM, SilentUI, make_agent, reply, tool_call
from test_team import WAIT, SubLLM, done


def test_undo_restores_and_deletes(tmp_path):
    (tmp_path / "a.py").write_text("old", encoding="utf-8")
    cps = Checkpoints(tmp_path)
    cps.begin("第一轮")
    for name, text in (("a.py", "new"), ("a.py", "newer"), ("b.py", "created")):
        p = tmp_path / name
        cps.before_write(p)
        p.write_text(text, encoding="utf-8")
        cps.after_write(p)
    cps.begin("第二轮：没改文件")
    result = cps.undo()
    assert result["label"] == "第一轮" and result["restored"] == ["a.py"] and result["deleted"] == ["b.py"]
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "old" and not (tmp_path / "b.py").exists()
    assert cps.undo()["label"] == "" and "没有可以撤销" in describe(cps.undo())


def test_undo_refuses_when_file_changed_afterwards(tmp_path):
    cps = Checkpoints(tmp_path)
    cps.begin("写 a")
    p = tmp_path / "a.py"
    cps.before_write(p)
    p.write_text("agent", encoding="utf-8")
    cps.after_write(p)
    p.write_text("用户手动改的", encoding="utf-8")
    result = cps.undo()
    assert result["conflicts"] == ["a.py"] and not result["deleted"] and p.exists()
    assert "又被修改过" in describe(result)
    assert cps.undo(force=True)["deleted"] == ["a.py"] and not p.exists()


def test_agent_undo_tells_model(tmp_path):
    (tmp_path / "x.py").write_text("v1\n", encoding="utf-8")
    agent, llm = make_agent(tmp_path, [
        reply(calls=[tool_call("r", "read_file", path="x.py")]),
        reply(calls=[tool_call("e", "edit_file", path="x.py", old_string="v1", new_string="v2")]),
        reply("改好了"),
        reply("知道了"),
    ])
    agent.run("把 v1 改成 v2")
    assert (tmp_path / "x.py").read_text(encoding="utf-8") == "v2\n"
    result = agent.undo()
    assert result["restored"] == ["x.py"] and (tmp_path / "x.py").read_text(encoding="utf-8") == "v1\n"
    agent.run("继续")
    assert "undid your file changes" in llm.seen[-1][-1]["content"] and "继续" in llm.seen[-1][-1]["content"]


def test_team_undo_covers_all_agents(tmp_path):
    plan = {"tasks": [{"id": "core", "role": "backend", "description": "写 core", "files": ["core.py"]}]}
    lead = [reply(calls=[tool_call("w", "write_file", path="notes.md", content="lead 写的")]),
            reply(calls=[tool_call("p", "plan_tasks", **plan)]),
            reply(calls=[tool_call("d", "dispatch", task_ids=["core"])]), WAIT,
            reply("完成")]
    core = [reply(calls=[tool_call("w", "write_file", path="core.py", content="x = 1\n")]), done("core 完成")]
    queue = [FakeLLM(lead), SubLLM(core)]
    team = Team(lambda: queue.pop(0), tmp_path, PermissionManager(ask=lambda *a: ("y", ""), auto=True),
                SilentUI(), max_steps=10, quality_roles=False)
    team.run("做吧")
    assert (tmp_path / "core.py").exists() and (tmp_path / "notes.md").exists()
    result = team.undo()
    assert sorted(result["deleted"]) == ["core.py", "notes.md"]
    assert team.lead._pending_note
