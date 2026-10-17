"""用脚本化的假 LLM 测试 agent 循环，不调用真实 API。"""
import json
from types import SimpleNamespace

from coder.agent import Agent, truncate
from coder.permissions import PermissionManager
from coder.tools import build_tools
from coder.workspace import Workspace


def tool_call(id_, name, **args):
    return SimpleNamespace(id=id_, function=SimpleNamespace(name=name, arguments=json.dumps(args)))


def reply(content="", calls=None):
    return SimpleNamespace(content=content, tool_calls=calls or None)


class FakeLLM:
    """按顺序返回预设的回复，并记录每次收到的消息。"""

    def __init__(self, replies):
        self.replies = list(replies)
        self.seen = []

    def chat(self, messages, tools, on_delta=None):
        self.seen.append([dict(m) for m in messages])
        return self.replies.pop(0)


class SilentUI:
    def __getattr__(self, name):
        return lambda *a, **k: None


def make_agent(tmp_path, replies, ask=None, auto=True):
    ws = Workspace(tmp_path)
    llm = FakeLLM(replies)
    perms = PermissionManager(ask=ask or (lambda n, p: ("y", "")), auto=auto)
    return Agent(llm, build_tools(ws), ws, perms, SilentUI(), max_steps=5), llm


def test_agent_writes_file_and_finishes(tmp_path):
    agent, llm = make_agent(tmp_path, [
        reply(calls=[tool_call("c1", "write_file", path="hello.py", content="print('hi')\n")]),
        reply("完成"),
    ])
    agent.run("写一个 hello world")
    assert (tmp_path / "hello.py").read_text() == "print('hi')\n"
    # 第二次调用模型时，应该已经能看到工具结果
    assert llm.seen[1][-1]["role"] == "tool"
    assert agent.messages[-1] == {"role": "assistant", "content": "完成"}


def test_tool_error_is_returned_to_model(tmp_path):
    agent, llm = make_agent(tmp_path, [
        reply(calls=[tool_call("c1", "read_file", path="missing.py")]),
        reply("文件不存在"),
    ])
    agent.run("读一下 missing.py")
    assert "文件不存在" in llm.seen[1][-1]["content"]


def test_rejection_feedback_reaches_model(tmp_path):
    agent, llm = make_agent(tmp_path, [
        reply(calls=[tool_call("c1", "write_file", path="a.py", content="x")]),
        reply("好的"),
    ], ask=lambda n, p: ("n", "文件名改成 b.py"), auto=False)
    agent.run("建个文件")
    assert not (tmp_path / "a.py").exists()
    assert "文件名改成 b.py" in llm.seen[1][-1]["content"]


def test_bad_json_args(tmp_path):
    bad = SimpleNamespace(id="c1", function=SimpleNamespace(name="read_file", arguments="{oops"))
    agent, llm = make_agent(tmp_path, [reply(calls=[bad]), reply("ok")])
    agent.run("x")
    assert "JSON" in llm.seen[1][-1]["content"]


def test_max_steps(tmp_path):
    loop = [reply(calls=[tool_call(f"c{i}", "list_dir")]) for i in range(5)]
    agent, llm = make_agent(tmp_path, loop)
    agent.run("x")
    assert len(llm.seen) == 5


def test_interrupt_fills_missing_tool_results(tmp_path):
    agent, _ = make_agent(tmp_path, [])
    agent.messages.append({"role": "assistant", "content": "", "tool_calls": [
        {"id": "c1", "type": "function", "function": {"name": "list_dir", "arguments": "{}"}},
        {"id": "c2", "type": "function", "function": {"name": "list_dir", "arguments": "{}"}},
    ]})
    agent.messages.append({"role": "tool", "tool_call_id": "c1", "content": "..."})
    agent.interrupt()
    assert agent.messages[-1] == {"role": "tool", "tool_call_id": "c2", "content": "用户中断了执行"}


def test_project_notes_loaded(tmp_path):
    (tmp_path / "AGENT.md").write_text("使用 pytest 运行测试", encoding="utf-8")
    agent, _ = make_agent(tmp_path, [])
    assert "使用 pytest 运行测试" in agent.messages[0]["content"]


def test_truncate_keeps_head_and_tail():
    out = truncate("A" * 100 + "B" * 100, 50)
    assert out.startswith("A") and out.endswith("B") and "省略" in out


def test_reasoning_passed_back_within_turn_and_dropped_on_next_turn(tmp_path):
    first = reply(calls=[tool_call("c1", "list_dir")])
    first.reasoning_content = "先看目录"
    agent, llm = make_agent(tmp_path, [first, reply("好了"), reply("第二轮")])
    agent.run("看看目录")
    # 同一轮里，下一次调用模型时带上了思考内容
    assert llm.seen[1][-2]["reasoning_content"] == "先看目录"
    agent.run("再来")
    assert not any("reasoning_content" in m for m in llm.seen[2])


def test_usage_accumulates(tmp_path):
    a, b = reply(calls=[tool_call("c1", "list_dir")]), reply("ok")
    a.usage = SimpleNamespace(prompt=100, completion=10, cached=50)
    b.usage = SimpleNamespace(prompt=200, completion=20, cached=150)
    agent, _ = make_agent(tmp_path, [a, b])
    agent.run("x")
    assert agent.usage == {"prompt": 300, "completion": 30, "cached": 200}


def test_cancel_during_streaming(tmp_path):
    from coder.agent import Cancelled

    class StreamingLLM(FakeLLM):
        def chat(self, messages, tools, on_delta=None):
            on_delta("text", "一半")
            agent.cancel()          # 模拟用户在生成过程中点停止
            on_delta("text", "另一半")
            raise AssertionError("不应该执行到这里")

    agent, _ = make_agent(tmp_path, [])
    agent.llm = StreamingLLM([])
    import pytest
    with pytest.raises(Cancelled):
        agent.run("x")


def test_user_message_with_images_uses_multimodal_content(tmp_path):
    agent, llm = make_agent(tmp_path, [reply("看到了")])
    agent.run("这是什么题", images=["data:image/png;base64,AAAA"])
    content = llm.seen[0][-1]["content"]
    assert content == [{"type": "text", "text": "这是什么题"},
                       {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}]
    # 没有图片时仍然是普通字符串
    agent.llm = FakeLLM([reply("ok")])
    agent.run("hi")
    assert agent.llm.seen[0][-1]["content"] == "hi"


def test_repeated_identical_calls_get_a_warning(tmp_path):
    same = [reply(calls=[tool_call(f"c{i}", "list_dir", path=".")]) for i in range(3)]
    agent, llm = make_agent(tmp_path, same + [reply("换个办法")])
    agent.run("x")
    tool_results = [m["content"] for m in agent.messages if m["role"] == "tool"]
    assert "[提醒]" not in tool_results[1] and "[提醒]" in tool_results[2]


def test_context_compaction_summarizes_early_history(tmp_path):
    from coder import context
    big = "很长的输出" * 2000  # 约 1 万 token
    (tmp_path / "big.txt").write_text(big, encoding="utf-8")
    script = [reply(calls=[tool_call(f"r{i}", "read_file", path="big.txt", limit=1)]) for i in range(3)]
    agent, llm = make_agent(tmp_path, script + [reply("早期摘要：读了 big.txt 三次"), reply("完成")])
    agent.context_limit = 3000
    agent.max_tool_output = 100_000
    # 让每次 read_file 都返回大段内容
    agent.tools["read_file"].run = lambda **kw: big
    agent.run("读三遍 big.txt")
    assert agent.compactions == 1
    summary_msgs = [m for m in agent.messages if "压缩为以下摘要" in str(m.get("content"))]
    assert summary_msgs and "早期摘要" in summary_msgs[0]["content"]
    # 摘要请求本身不带工具，记录是纯文本
    summary_call = [s for s in llm.seen if len(s) == 1][0]
    assert "【用户】读三遍 big.txt" in summary_call[0]["content"]
    # 压缩后的消息顺序合法：每个 tool 消息前面都有发起调用的 assistant
    ids = set()
    for m in agent.messages:
        if m["role"] == "assistant":
            ids |= {c["id"] for c in m.get("tool_calls", [])}
        if m["role"] == "tool":
            assert m["tool_call_id"] in ids
    assert context.estimate_tokens(agent.messages) < context.estimate_tokens([{"role": "user", "content": big * 3}])


def test_prune_and_split_helpers():
    from coder import context
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
    for i in range(8):
        msgs.append({"role": "assistant", "content": "", "tool_calls": [
            {"id": f"c{i}", "type": "function", "function": {"name": "read_file", "arguments": "{}"}}]})
        msgs.append({"role": "tool", "tool_call_id": f"c{i}", "content": "x" * 5000})
    removed = context.prune_tool_outputs(msgs)
    assert removed > 0
    tool_contents = [m["content"] for m in msgs if m["role"] == "tool"]
    assert all(len(c) < 1000 for c in tool_contents[:2]) and all(len(c) == 5000 for c in tool_contents[-6:])
    split = context.find_split(msgs, keep_tokens=4000)
    assert msgs[split]["role"] in ("user", "assistant")
    assert context.estimate_tokens(msgs[split:]) <= 4000


def test_stub_bulky_args_keeps_recent_and_structure():
    from coder import context
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
    for i in range(4):
        args = json.dumps({"path": f"f{i}.py", "content": "x = 1\n" * 1000})
        msgs.append({"role": "assistant", "content": "", "tool_calls": [
            {"id": f"c{i}", "type": "function", "function": {"name": "write_file", "arguments": args}}]})
        msgs.append({"role": "tool", "tool_call_id": f"c{i}", "content": "已写入"})
    removed = context.stub_bulky_args(msgs, keep_recent=2)
    assert removed > 0
    calls = [m["tool_calls"][0]["function"] for m in msgs if m["role"] == "assistant"]
    old, recent = [json.loads(c["arguments"]) for c in calls[:2]], [json.loads(c["arguments"]) for c in calls[2:]]
    assert all(a["path"].endswith(".py") and "已省略" in a["content"] for a in old)  # 路径保留，内容换成占位
    assert all(a["content"] == "x = 1\n" * 1000 for a in recent)
    assert context.stub_bulky_args(msgs, keep_recent=2) == 0  # 重复调用不再变化


def test_compaction_keeps_request_and_touched_files(tmp_path):
    big = "很长的输出" * 2000
    request = "按规格实现：金额保留两位小数，负数报错"
    script = [reply(calls=[tool_call("w", "write_file", path="a.py", content="x = 1\n")])]
    script += [reply(calls=[tool_call("r", "read_file", path="a.py")]), reply("摘要：写了 a.py"), reply("完成")]
    agent, llm = make_agent(tmp_path, script)
    agent.context_limit = 3000
    agent.max_tool_output = 100_000
    agent.tools["read_file"].run = lambda **kw: big
    agent.run(request)
    summary = [m["content"] for m in agent.messages if "压缩为以下摘要" in str(m.get("content"))][0]
    assert request in summary and "a.py" in summary  # 原始要求原文和改过的文件由程序写入，不靠模型转述
    assert agent.touched_files == ["a.py"]


def test_no_back_to_back_summaries(tmp_path):
    """刚压缩过就不再调用模型生成摘要，只做无损裁剪，避免反复压缩。"""
    import coder.agent as agent_module
    big = "很长的输出" * 2000
    # 第 2 步前压缩一次；之后每一步上下文仍然超限，但距离上次摘要太近，不再生成摘要
    script = [reply(calls=[tool_call("r0", "read_file", path="a")]), reply("摘要一")]
    script += [reply(calls=[tool_call(f"r{i}", "read_file", path="a")]) for i in (1, 2)] + [reply("完成")]
    agent, llm = make_agent(tmp_path, script)
    agent.max_steps = 10
    agent.context_limit = 3000
    agent.max_tool_output = 100_000
    agent.tools["read_file"].run = lambda **kw: big
    agent.run("读文件")
    summary_calls = [s for s in llm.seen if len(s) == 1]
    assert agent.compactions == 1 and len(summary_calls) == 1
    assert agent_module.SUMMARY_GAP > 2


def test_compaction_drops_well_below_threshold_and_keeps_cache_prefix(tmp_path):
    """一次降到阈值的 60% 以下：之后几步不会再触发，前面的消息不再被改动（缓存前缀保持稳定）。"""
    import copy
    agent, _ = make_agent(tmp_path, [])
    agent.context_limit = 12_000
    for i in range(10):
        agent.messages.append({"role": "assistant", "content": "", "tool_calls": [
            {"id": f"c{i}", "type": "function", "function": {"name": "read_file", "arguments": "{}"}}]})
        agent.messages.append({"role": "tool", "tool_call_id": f"c{i}", "content": "x" * 6000})
    agent._last_summary_step = agent.steps  # 刚压缩过：这次不能生成摘要，只能无损裁剪
    agent._maybe_compact()
    assert agent._estimate() < agent.context_limit * 0.6
    before = copy.deepcopy(agent.messages)
    for i in range(3):  # 之后又进行了几步
        agent.messages.append({"role": "assistant", "content": "", "tool_calls": [
            {"id": f"n{i}", "type": "function", "function": {"name": "read_file", "arguments": "{}"}}]})
        agent.messages.append({"role": "tool", "tool_call_id": f"n{i}", "content": "y" * 3000})
        agent._maybe_compact()
    assert agent.messages[:len(before)] == before  # 前面的消息一条都没被改动


def test_truncated_reply_is_not_treated_as_done(tmp_path):
    """回复达到输出上限被截断时没有工具调用，不能当成任务完成：提醒模型继续，并把回复写短。"""
    cut = reply("我现在开始写 shop.py……")
    cut.finish_reason = "length"
    agent, llm = make_agent(tmp_path, [
        cut,
        reply(calls=[tool_call("w", "write_file", path="shop.py", content="x = 1\n")]),
        reply("完成"),
    ])
    agent.run("实现 shop")
    assert (tmp_path / "shop.py").is_file()
    assert "cut off" in llm.seen[1][-1]["content"]


def test_repeated_truncation_stops(tmp_path):
    replies = []
    for _ in range(5):
        r = reply("想了很久……")
        r.finish_reason = "length"
        replies.append(r)
    agent, llm = make_agent(tmp_path, replies)
    agent.run("x")
    assert len(llm.seen) == 4  # 最多提醒 3 次


# ---------------------------------------------------------------- 工具调用格式错误

def test_bad_json_args_are_not_sent_back_to_the_model(tmp_path):
    """参数不是合法 JSON：不执行；发回历史时换成合法的空参数，否则下一次调用整个对话被服务商拒绝（400）。"""
    bad = SimpleNamespace(id="c1", function=SimpleNamespace(name="write_file", arguments='{"path": "a.py", "content": "未结束'))
    agent, llm = make_agent(tmp_path, [reply(calls=[bad]), reply("ok")])
    agent.run("x")
    sent = next(m for m in llm.seen[1] if m.get("tool_calls"))["tool_calls"][0]
    assert json.loads(sent["function"]["arguments"]) == {}
    assert "参数不是合法的 JSON" in llm.seen[1][-1]["content"] and not (tmp_path / "a.py").exists()


def test_tool_calls_in_a_truncated_reply_are_not_executed(tmp_path):
    """回复被输出上限截断：这条消息里的工具调用一律不执行（补出来的参数可能能通过校验，但内容不完整）。"""
    cut = SimpleNamespace(content="", finish_reason="length",
                          tool_calls=[tool_call("c1", "write_file", path="a.py", content="def f(")])
    agent, llm = make_agent(tmp_path, [cut, reply("好")])
    agent.run("x")
    assert not (tmp_path / "a.py").exists() and "被截断" in llm.seen[1][-1]["content"]


def test_stops_after_repeated_format_errors(tmp_path):
    bad = lambda i: SimpleNamespace(id=f"c{i}", function=SimpleNamespace(name="read_file", arguments="{oops"))  # noqa: E731
    agent, llm = make_agent(tmp_path, [reply(calls=[bad(i)]) for i in range(5)])
    agent.run("x")
    assert len(llm.seen) == 3   # 连续 3 步格式错误就停下，不再空转


# ---------------------------------------------------------------- verify-on-stop

def test_verify_on_stop(tmp_path):
    """改了代码、之后没有成功运行过验证就想结束：否决一次，让它去验证；验证过就可以结束。"""
    agent, llm = make_agent(tmp_path, [
        reply(calls=[tool_call("c1", "write_file", path="add.py", content="def add(a, b):\n    return a + b\n")]),
        reply("写好了"),
        reply(calls=[tool_call("c2", "run_command", command="python -c \"import add\"")]),
        reply("验证过了")])
    agent.verify_on_stop = True
    agent.run("写 add")
    notes = [m["content"] for m in agent.messages if m["role"] == "user" and "没有成功运行过验证" in str(m["content"])]
    assert len(notes) == 1 and "add.py" in notes[0]
    assert agent.messages[-1]["content"] == "验证过了"


def test_verify_on_stop_vetoes_only_once_and_ignores_docs(tmp_path):
    agent, llm = make_agent(tmp_path, [
        reply(calls=[tool_call("c1", "write_file", path="add.py", content="x = 1\n")]),
        reply("写好了"), reply("这个项目没有测试，没法验证")])
    agent.verify_on_stop = True
    agent.run("x")
    assert len(llm.seen) == 3                     # 说明原因以后就可以结束
    agent2, llm2 = make_agent(tmp_path, [
        reply(calls=[tool_call("c1", "write_file", path="NOTES.md", content="# 说明\n")]), reply("写好了")])
    agent2.verify_on_stop = True
    agent2.run("x")
    assert len(llm2.seen) == 2                    # 只改了文档，不要求验证


# ---------------------------------------------------------------- 插话

def test_user_can_steer_while_the_agent_works(tmp_path):
    """运行中插话：在当前这步的工具执行完后插入对话；想结束时刚好有插话也先处理。"""
    agent, llm = make_agent(tmp_path, [
        reply(calls=[tool_call("c1", "list_dir", path=".")]), reply("看完了"), reply("好的，改用 pytest")])
    original = llm.chat

    def chat(messages, tools, on_delta=None):
        if len(llm.seen) == 1:
            agent.steer("测试用 pytest")   # 第一步执行工具时用户插话
        return original(messages, tools, on_delta)
    llm.chat = chat
    agent.run("看看项目")
    steer = [i for i, m in enumerate(llm.seen[2]) if m["role"] == "user" and "测试用 pytest" in str(m["content"])]
    assert steer and llm.seen[2][-1]["content"].startswith("[用户在你工作时补充")


# ---------------------------------------------------------------- 循环检测

def test_detects_cycles_and_repeated_failures(tmp_path):
    a = lambda i: tool_call(f"a{i}", "list_dir", path=".")                      # noqa: E731
    b = lambda i: tool_call(f"b{i}", "read_file", path="missing.py")            # noqa: E731
    agent, llm = make_agent(tmp_path, [reply(calls=[a(i), b(i)]) for i in range(3)] + [reply("换个办法")])
    agent.max_steps = 10
    agent.run("x")
    results = [m["content"] for m in agent.messages if m["role"] == "tool"]
    assert any("你在重复同一组操作" in r for r in results)
    assert any("已经失败了 3 次" in r for r in results)
