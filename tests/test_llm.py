"""测试流式响应的拼装：用假的 chunk 序列代替真实 API。"""
from types import SimpleNamespace as NS

from coder.config import Config
from coder.llm import LLM


def chunk(content=None, reasoning=None, tool_calls=None, usage=None):
    choices = [] if usage else [NS(delta=NS(content=content, reasoning_content=reasoning, tool_calls=tool_calls))]
    return NS(choices=choices, usage=usage)


def tc(index, id=None, name=None, args=None):
    return NS(index=index, id=id, function=NS(name=name, arguments=args))


class FakeStream(list):
    def close(self):
        pass


def make_llm(chunks):
    llm = LLM(Config(api_key="test"))
    llm.client = NS(chat=NS(completions=NS(create=lambda **kw: FakeStream(chunks))))
    return llm


def test_assembles_text_reasoning_tool_calls_and_usage():
    llm = make_llm([
        chunk(reasoning="先想"), chunk(reasoning="一想"),
        chunk(content="好的，"), chunk(content="我来看看"),
        chunk(tool_calls=[tc(0, id="call_1", name="read_", args='{"pa')]),
        chunk(tool_calls=[tc(0, name="file", args='th": "a.py"}')]),
        chunk(tool_calls=[tc(1, id="call_2", name="list_dir", args="{}")]),
        chunk(usage=NS(prompt_tokens=100, completion_tokens=20, prompt_cache_hit_tokens=64)),
    ])
    deltas = []
    msg = llm.chat([], [], on_delta=lambda k, t: deltas.append((k, t)))
    assert msg.reasoning_content == "先想一想"
    assert msg.content == "好的，我来看看"
    assert [(c.id, c.function.name, c.function.arguments) for c in msg.tool_calls] == [
        ("call_1", "read_file", '{"path": "a.py"}'), ("call_2", "list_dir", "{}")]
    assert (msg.usage.prompt, msg.usage.completion, msg.usage.cached) == (100, 20, 64)
    assert deltas[0] == ("reasoning", "先想") and ("text", "我来看看") in deltas


def test_plain_reply_without_tools():
    msg = make_llm([chunk(content="你好")]).chat([], [])
    assert msg.content == "你好" and msg.tool_calls is None and msg.reasoning_content is None


def test_retries_transient_errors(monkeypatch):
    import httpx
    from openai import APIConnectionError

    from coder import llm as llm_module
    monkeypatch.setattr(llm_module.time, "sleep", lambda s: None)
    attempts = []

    class FlakyStream(list):
        """第二次请求：流式输出到一半时连接超时。"""
        def __iter__(self):
            yield chunk(content="半截")
            raise httpx.ReadTimeout("卡住了")

        def close(self):
            pass

    def create(**kw):
        attempts.append(1)
        if len(attempts) == 1:
            raise APIConnectionError(request=httpx.Request("POST", "http://x"))
        if len(attempts) == 2:
            return FlakyStream()
        return FakeStream([chunk(content="完整回复")])

    llm = make_llm([])
    llm.client = NS(chat=NS(completions=NS(create=create)))
    msg = llm.chat([], [])
    assert msg.content == "完整回复" and len(attempts) == 3 and llm.retries == 2


def test_gives_up_after_retries(monkeypatch):
    import httpx
    import pytest
    from openai import APIConnectionError

    from coder import llm as llm_module
    monkeypatch.setattr(llm_module.time, "sleep", lambda s: None)

    def create(**kw):
        raise APIConnectionError(request=httpx.Request("POST", "http://x"))

    llm = make_llm([])
    llm.client = NS(chat=NS(completions=NS(create=create)))
    with pytest.raises(APIConnectionError):
        llm.chat([], [])
    assert llm.retries == len(llm_module.RETRY_DELAYS)


def test_cancel_is_not_retried():
    class Stop(Exception):
        pass

    def on_delta(kind, text):
        raise Stop()

    llm = make_llm([chunk(content="x")])
    import pytest
    with pytest.raises(Stop):
        llm.chat([], [], on_delta=on_delta)
    assert llm.retries == 0


def test_no_extra_headers_for_any_provider():
    """项目只按标准 OpenAI 兼容接口调用，不加额外请求头。"""
    for provider in ("deepseek", "custom"):
        llm = LLM(Config(api_key="k", base_url="http://127.0.0.1:8000/v1", provider=provider))
        assert not llm.client.default_headers["User-Agent"].startswith("coder/")  # SDK 默认
        seen = []
        llm.client = NS(chat=NS(completions=NS(create=lambda **kw: seen.append(kw) or FakeStream([chunk(content="好")]))))
        llm.chat([], [])
        assert "extra_headers" not in seen[0]


def test_provider_from_env(monkeypatch):
    from coder.config import Config as Cfg

    for k in ("CODER_PROVIDER", "CODER_BASE_URL", "CODER_MODEL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("CODER_BASE_URL", "https://api.deepseek.com")  # 旧配置只写了地址：按地址识别
    assert Cfg.from_env().provider == "deepseek"
    monkeypatch.setenv("CODER_BASE_URL", "https://my-proxy.example.com/v1")
    assert Cfg.from_env().provider == "custom"
    monkeypatch.delenv("CODER_BASE_URL")
    monkeypatch.setenv("CODER_PROVIDER", "deepseek")  # 只选了服务商：用它的默认地址
    assert Cfg.from_env().base_url == "https://api.deepseek.com"


def test_save_settings_keeps_other_lines(tmp_path, monkeypatch):
    from coder.config import save_settings

    env = tmp_path / ".env"
    env.write_text("# 注释\nCODER_API_KEY=old\n# CODER_MODEL=注释掉的不动\nCODER_MAX_STEPS=40\n", encoding="utf-8")
    for k in ("CODER_API_KEY", "CODER_MODEL", "CODER_PROVIDER"):  # 测试结束后恢复环境变量
        monkeypatch.setenv(k, "old")
    save_settings({"CODER_API_KEY": "new", "CODER_MODEL": "m", "CODER_PROVIDER": "deepseek"}, env)
    assert env.read_text(encoding="utf-8").splitlines() == [
        "# 注释", "CODER_API_KEY=new", "# CODER_MODEL=注释掉的不动", "CODER_MAX_STEPS=40",
        "CODER_MODEL=m", "CODER_PROVIDER=deepseek"]
    import os
    assert os.environ["CODER_API_KEY"] == "new"


def test_retry_wait_can_be_cancelled(monkeypatch):
    """等待重试期间点停止：立即中断，不用等这一轮等待结束。"""
    import httpx
    import pytest
    from openai import APIConnectionError

    from coder import llm as llm_module
    slept = []
    monkeypatch.setattr(llm_module.time, "sleep", lambda s: slept.append(s))

    class Stop(Exception):
        pass

    def create(**kw):
        raise APIConnectionError(request=httpx.Request("POST", "http://x"))

    llm = make_llm([])
    llm.client = NS(chat=NS(completions=NS(create=create)))
    calls = []

    def on_delta(kind, text):
        calls.append(text)
        if len(calls) == 3:  # 等待到一半时用户点了停止
            raise Stop()
    with pytest.raises(Stop):
        llm.chat([], [], on_delta=on_delta)
    assert calls == ["", "", ""] and len(slept) == 2 and sum(slept) < llm_module.RETRY_DELAYS[0]
    assert sum(llm_module.RETRY_DELAYS) >= 120  # 能扛住两分钟左右的网络中断


def test_temperature_fallback_for_models_that_reject_it():
    """有的模型只接受默认的 temperature（比如 Kimi 的代码模型只允许 1）：被拒绝后不传这个参数重试，并记住。"""
    import httpx
    from openai import BadRequestError
    calls = []

    def create(**kw):
        calls.append(kw.get("temperature", "omitted"))
        if "temperature" in kw:
            req = httpx.Request("POST", "http://x/v1/chat/completions")
            raise BadRequestError("invalid temperature: only 1 is allowed for this model",
                                  response=httpx.Response(400, request=req), body=None)
        return FakeStream([chunk(content="好")])

    llm = LLM(Config(api_key="test"))
    llm.client = NS(chat=NS(completions=NS(create=create)))
    assert llm.chat([], []).content == "好" and llm.chat([], []).content == "好"
    assert calls == [0, "omitted", "omitted"]  # 第二次调用直接不传，不再试错


def test_cached_tokens_in_openai_format():
    msg = make_llm([chunk(content="x"), chunk(usage=NS(prompt_tokens=100, completion_tokens=5,
                                                        prompt_tokens_details=NS(cached_tokens=80)))]).chat([], [])
    assert msg.usage.cached == 80


def test_inline_think_block_is_shown_as_reasoning_but_sent_back_unchanged():
    """MiniMax 等模型把思考过程用 <think> 写在正文开头：界面上显示成思考过程，发回历史时保持原样。"""
    from coder.agent import Agent
    parts = ["<thi", "nk>先看看", "文件</th", "ink>\n\n好的，", "我来读取。"]
    llm = make_llm([chunk(content=p) for p in parts])
    deltas = []
    msg = llm.chat([], [], on_delta=lambda k, t: deltas.append((k, t)))
    assert msg.reasoning_content == "先看看文件" and msg.content == "好的，我来读取。"
    assert all(k == "reasoning" for k, t in deltas if "看" in t) and ("text", "我来读取。") in deltas
    assert Agent._assistant_message(msg)[0]["content"] == "".join(parts)
    assert "reasoning_content" not in Agent._assistant_message(msg)[0]
    plain = make_llm([chunk(content="答案里提到 <think> 标签")]).chat([], [])
    assert plain.content == "答案里提到 <think> 标签" and plain.reasoning_content is None and plain.raw_content is None
