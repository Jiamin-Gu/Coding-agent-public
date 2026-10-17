"""评测运行器的测试：用脚本化的假模型"做题"，验证工作区隔离、隐藏测试判分和结果统计。"""
import json
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

from coder import eval as ev

TASK = ev.TASKS_DIR / "algo_merge_intervals"
SOLUTION = (TASK / "solution" / "intervals.py").read_text(encoding="utf-8")


def tool_call(id_, name, **args):
    return SimpleNamespace(id=id_, function=SimpleNamespace(name=name, arguments=json.dumps(args)))


class ScriptedLLM:
    def __init__(self, replies):
        self.replies = list(replies)

    def chat(self, messages, tools, on_delta=None):
        r = self.replies.pop(0)
        r.usage = SimpleNamespace(prompt=100, completion=10, cached=0)
        return r


def make_args(**kw):
    defaults = dict(no_read_guard=False, no_compact=False, max_steps=10, context_limit=60_000,
                    repeat=1, keep=False)
    return Namespace(**{**defaults, **kw})


def test_correct_solution_passes(tmp_path):
    llm = ScriptedLLM([
        SimpleNamespace(content="", tool_calls=[tool_call("c1", "write_file", path="intervals.py", content=SOLUTION)]),
        SimpleNamespace(content="完成", tool_calls=None),
    ])
    r = ev.run_task(TASK, lambda: llm, make_args(), tmp_path)
    assert r.passed and r.steps == 2 and r.tool_calls == 1 and r.prompt_tokens == 200
    saved = json.loads((tmp_path / "trajectories" / "algo_merge_intervals.json").read_text(encoding="utf-8"))
    assert saved["result"]["passed"] is True and saved["messages"][0]["role"] == "system"
    # token 账本：每次调用一条记录，带上下文构成
    log = saved["call_log"]
    assert [c["step"] for c in log] == [1, 2] and log[0]["prompt"] == 100
    assert set(log[0]["composition"]) == {"system", "tools", "user", "assistant", "tool_results"}
    assert log[1]["composition"]["tool_results"] > 0 and log[0]["composition"]["tool_results"] == 0


def test_wrong_solution_fails_and_hidden_tests_not_visible(tmp_path):
    seen = {}

    class Peek(ScriptedLLM):
        def chat(self, messages, tools, on_delta=None):
            # agent 工作期间，隐藏测试不应该出现在工作区里
            ws = Path(messages[0]["content"].split("Workspace root: ")[1].split("\n")[0])
            seen["hidden_present"] = (ws / ev.TEST_DIR_NAME).exists()
            return super().chat(messages, tools, on_delta)

    llm = Peek([
        SimpleNamespace(content="", tool_calls=[tool_call(
            "c1", "write_file", path="intervals.py", content="def merge_intervals(x):\n    return x\n")]),
        SimpleNamespace(content="完成", tool_calls=None),
    ])
    r = ev.run_task(TASK, lambda: llm, make_args(), tmp_path)
    assert not r.passed and seen["hidden_present"] is False
    assert "failed" in r.test_output


def test_analyze_report(tmp_path):
    from coder.analyze import analyze
    llm = ScriptedLLM([
        SimpleNamespace(content="", tool_calls=[tool_call("c1", "run_command", command="echo hi")]),
        SimpleNamespace(content="", tool_calls=[tool_call("c2", "run_command", command="echo hi")]),
        SimpleNamespace(content="", tool_calls=[tool_call("c3", "write_file", path="intervals.py", content=SOLUTION)]),
        SimpleNamespace(content="完成", tool_calls=None),
    ])
    ev.run_task(TASK, lambda: llm, make_args(), tmp_path)
    report = analyze(tmp_path)
    assert "## 输入 token 的构成" in report and "工具定义" in report
    assert "重复执行完全相同的命令：共 1 次" in report
    assert "通过（1 次）" in report


def test_replay_rebuilds_delivered_code(tmp_path):
    from coder import replay
    llm = ScriptedLLM([
        SimpleNamespace(content="", tool_calls=[tool_call("c1", "write_file", path="intervals.py", content="def merge_intervals(x):\n    return x\n")]),
        SimpleNamespace(content="", tool_calls=[tool_call("c2", "write_file", path="_tmp_check.py", content="print(1)\n")]),
        SimpleNamespace(content="", tool_calls=[tool_call("c3", "read_file", path="intervals.py")]),
        SimpleNamespace(content="", tool_calls=[tool_call("c4", "edit_file", path="intervals.py",
                                                          old_string="def merge_intervals(x):\n    return x\n", new_string=SOLUTION)]),
        SimpleNamespace(content="", tool_calls=[tool_call("c5", "run_command", command='python -c "import os; os.remove(\'_tmp_check.py\')"')]),
        SimpleNamespace(content="完成", tool_calls=None),
    ])
    ev.run_task(TASK, lambda: llm, make_args(), tmp_path)
    t = json.loads((tmp_path / "trajectories" / "algo_merge_intervals.json").read_text(encoding="utf-8"))
    code = tmp_path / "replayed"
    deleted = replay.replay(TASK, t, code)
    assert deleted == ["_tmp_check.py"] and not (code / "_tmp_check.py").exists()
    assert (code / "intervals.py").read_text(encoding="utf-8") == SOLUTION
    assert replay.verify(TASK, code)[0] is True
    # 删除命令的识别只看删除命令自己的参数
    assert replay.deleted_targets("del todos.json && python todo.py list") == ["todos.json"]
    assert not replay.matches("expr.py", "_test_expr.py") and replay.matches("_a.py", "_*.py")


def test_summary_table():
    results = [ev.Result(task="a", passed=True, steps=3), ev.Result(task="b", passed=False, steps=5)]
    md = ev.summarize(results, "label")
    assert "1/2（50%）" in md and "| a | ✅ |" in md and "| b | ❌ |" in md


def test_team_mode_eval_and_replay(tmp_path):
    """团队模式：主 agent 派一个子 agent 写代码；轨迹带上黑板和操作日志，重放按操作日志还原。"""
    from coder import replay
    plan = {"tasks": [
        {"id": "t", "role": "tester", "description": "写验收测试", "files": ["tests/acceptance/test_intervals.py"]},
        {"id": "algo", "role": "cli", "description": "实现 merge_intervals", "files": ["intervals.py"], "depends": ["t"]},
        {"id": "sec", "role": "security", "description": "安全审查", "files": [], "depends": ["algo"]}],
        "contracts": [{"name": "merge_intervals", "text": "merge_intervals(list[list[int]]) -> list[list[int]]"}]}
    def say(text):
        return SimpleNamespace(content=text, tool_calls=None)

    def call(id_, name, **kw):
        return SimpleNamespace(content="", tool_calls=[tool_call(id_, name, **kw)])

    def done(summary):
        return call("ct", "complete_task", summary=summary, verification="运行了测试")
    # 每个 agent 一份脚本（派发不阻塞：主 agent 和子 agent 同时在跑，不能共用一份按顺序弹出的脚本）
    scripts = [
        [call("p", "plan_tasks", **plan), call("d1", "dispatch", task_ids=["t"]), say("等测试"),
         call("d2", "dispatch", task_ids=["algo"]), say("等实现"), call("d3", "dispatch", task_ids=["sec"]),
         say("等审查"), say("全部完成")],
        [call("wt", "write_file", path="tests/acceptance/test_intervals.py", content="def test_placeholder():\n    pass\n"),
         done("测试写好了")],
        [call("w", "write_file", path="intervals.py", content=SOLUTION),
         call("x", "write_file", path="other.py", content="越权"), done("algo 完成")],
        [call("y", "write_file", path="intervals.py", content="改坏"), done("未发现安全问题")],
    ]
    class SubScripted(ScriptedLLM):  # 子 agent：第一次调用前稍等，主 agent 先拿到"已派出"再等汇报（结果稳定）
        def chat(self, messages, tools, on_delta=None):
            import time
            if not getattr(self, "_waited", False):
                self._waited = True
                time.sleep(0.05)
            return super().chat(messages, tools, on_delta)
    queue = [ScriptedLLM(scripts[0])] + [SubScripted(s) for s in scripts[1:]]
    args = make_args()
    args.team = "auto"
    r = ev.run_task(TASK, lambda: queue.pop(0), args, tmp_path)
    # 安全审查只读：它试图改代码被拒绝，代码保持实现者写的版本；测试和安全审查都出场了，不会触发提醒
    assert r.passed and r.steps == 8 + 2 + 3 + 2 and r.tool_errors == 2
    t = json.loads((tmp_path / "trajectories" / "algo_merge_intervals.json").read_text(encoding="utf-8"))
    assert t["team"]["board"]["tasks"]["algo"]["status"] == "done"
    assert {c["agent"] for c in t["call_log"]} == {"lead", "t", "algo", "sec"}
    code = tmp_path / "replayed"
    replay.replay(TASK, t, code)
    assert (code / "intervals.py").read_text(encoding="utf-8") == SOLUTION and not (code / "other.py").exists()
