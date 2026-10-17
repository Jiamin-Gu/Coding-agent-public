"""LLM 客户端。DeepSeek 兼容 OpenAI 协议，所以直接用 openai SDK，换别家模型只需改 base_url。"""
import time
from types import SimpleNamespace
from typing import Callable

import httpx
from openai import APIConnectionError, BadRequestError, InternalServerError, OpenAI, RateLimitError

from .config import Config

# 流式回调：(类型 "text" 或 "reasoning", 新增的文字)
DeltaFn = Callable[[str, str], None]

# 超时：read 是"两次收到数据之间最多等多久"。流式输出时，超过这个时间没有新数据就认为连接卡住了。
# SDK 默认整整 10 分钟，再加自动重试，网络卡住时 agent 会一动不动地等半个小时
TIMEOUT = httpx.Timeout(connect=15.0, read=90.0, write=30.0, pool=15.0)
# 临时性错误（网络中断、超时、限流、服务端错误）的重试间隔（秒）
# 网络短暂中断（比如电脑休眠唤醒、代理重连）可能持续一两分钟，重试的总等待时间要覆盖这种情况
RETRY_DELAYS = (2, 5, 10, 20, 30, 60)
TRANSIENT_ERRORS = (APIConnectionError, InternalServerError, RateLimitError, httpx.TransportError)


class LLM:
    def __init__(self, cfg: Config):
        # 重试由下面的 chat() 自己处理：SDK 的自动重试管不到流式输出中途断开的情况
        self.client = OpenAI(api_key=cfg.api_key, base_url=cfg.base_url, timeout=TIMEOUT, max_retries=0)
        self.model = cfg.model
        self.provider = cfg.provider
        self.base_url = cfg.base_url
        self.retries = 0  # 累计重试次数（评测报告会用到）
        # 用 0 让输出尽量稳定；有的模型只接受默认值（比如 Kimi 的代码模型只允许 1），被拒绝后自动调整并记住
        self.temperature: float | None = 0

    def chat(self, messages: list[dict], tools: list[dict], on_delta: DeltaFn | None = None):
        """流式调用模型，边生成边通过 on_delta 推送文字，最后返回完整消息。

        返回的对象有 content / reasoning_content / tool_calls / usage 四个字段。
        回调里抛出的异常（比如用户点了停止）会中断生成。
        网络超时、连接中断、限流、服务端错误会自动重试几次；中途断开时，已经推送的部分文字会在重试后重新输出。
        """
        for attempt in range(len(RETRY_DELAYS) + 1):
            try:
                return self._chat_once(messages, tools, on_delta)
            except BadRequestError as e:
                if "temperature" not in str(e).lower() or self.temperature == 1:
                    raise
                # 先试不传（用模型的默认值），还不行就用 1
                self.temperature = None if self.temperature is not None else 1
            except TRANSIENT_ERRORS:
                if attempt == len(RETRY_DELAYS):
                    raise
                self.retries += 1
                self._wait(RETRY_DELAYS[attempt], on_delta)

    @staticmethod
    def _wait(seconds: float, on_delta: DeltaFn | None) -> None:
        """等待重试。分成小段睡，每段之前调用一次 on_delta（空文字，界面不会显示），
        让调用方有机会检查停止标志：用户点停止时立即中断，而不是等到这一轮等待结束。"""
        steps = max(1, int(seconds / 0.5))
        for _ in range(steps):
            if on_delta:
                on_delta("text", "")
            time.sleep(seconds / steps)

    def _chat_once(self, messages: list[dict], tools: list[dict], on_delta: DeltaFn | None):
        kwargs = {"tools": tools} if tools else {}  # 压缩摘要等场景不需要工具
        stream = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=True,
            stream_options={"include_usage": True},
            **({"temperature": self.temperature} if self.temperature is not None else {}),
            **kwargs,
        )
        content, reasoning, raw = [], [], []
        finish = None  # 结束原因：stop 正常结束，length 达到输出上限被截断
        think = ThinkSplitter()  # 有的模型（如 MiniMax）把思考过程用 <think> 写在正文开头
        calls: dict[int, dict] = {}  # 工具调用按 index 分片到达，需要拼起来
        usage = None
        try:
            for chunk in stream:
                if chunk.usage:
                    usage = chunk.usage
                if not chunk.choices:
                    continue
                finish = getattr(chunk.choices[0], "finish_reason", None) or finish
                delta = chunk.choices[0].delta
                # 思考模型会先输出 reasoning_content（思考过程），再输出正文
                r = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None)  # 不同服务商字段名不同
                if r:
                    reasoning.append(r)
                    if on_delta:
                        on_delta("reasoning", r)
                if delta.content:
                    raw.append(delta.content)
                    for kind, text in think.feed(delta.content):
                        (reasoning if kind == "reasoning" else content).append(text)
                        if on_delta:
                            on_delta(kind, text)
                for tc in delta.tool_calls or []:
                    c = calls.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
                    if tc.id:
                        c["id"] = tc.id
                    if tc.function and tc.function.name:
                        c["name"] += tc.function.name
                    if tc.function and tc.function.arguments:
                        c["arguments"] += tc.function.arguments
            for kind, text in think.flush():
                (reasoning if kind == "reasoning" else content).append(text)
                if on_delta:
                    on_delta(kind, text)
        finally:
            stream.close()

        tool_calls = [
            SimpleNamespace(id=c["id"], function=SimpleNamespace(name=c["name"], arguments=c["arguments"]))
            for _, c in sorted(calls.items())
        ] or None
        for i, c in enumerate(tool_calls or []):
            if not c.id:  # 个别服务商不给工具调用编号，API 要求结果和调用一一对应，补一个
                c.id = f"call_{i}_{len(messages)}"
        return SimpleNamespace(
            content="".join(content).lstrip("\n") if think.found else "".join(content),
            reasoning_content="".join(reasoning) or None,
            # 正文里带 <think> 的模型：发回历史时保持原样（官方建议多轮工具调用时保留思考内容）
            raw_content="".join(raw) if think.found else None,
            finish_reason=finish,
            tool_calls=tool_calls,
            usage=SimpleNamespace(
                prompt=usage.prompt_tokens,
                completion=usage.completion_tokens,
                cached=cached_tokens(usage),
            ) if usage else None,
        )


def cached_tokens(usage) -> int:
    """命中缓存的输入 token 数。DeepSeek 用 prompt_cache_hit_tokens，OpenAI 格式（Kimi、Qwen 等）用
    prompt_tokens_details.cached_tokens。命中部分价格低很多。"""
    hit = getattr(usage, "prompt_cache_hit_tokens", None)
    if hit:
        return hit
    details = getattr(usage, "prompt_tokens_details", None)
    if isinstance(details, dict):
        return details.get("cached_tokens") or 0
    return getattr(details, "cached_tokens", 0) or 0


class ThinkSplitter:
    """把正文开头 <think>…</think> 里的思考过程分出来（流式：标签可能被切在两个片段之间）。
    只认正文最开头的思考块，正文中间出现的 "<think>" 字样当普通文字。"""
    OPEN, CLOSE = "<think>", "</think>"

    def __init__(self):
        self.state = "start"  # start：还没看到正文；think：在思考块里；text：普通正文
        self.buf = ""
        self.found = False

    def feed(self, text: str) -> list[tuple[str, str]]:
        self.buf += text
        out: list[tuple[str, str]] = []
        while self.buf:
            if self.state == "start":
                stripped = self.buf.lstrip()
                if stripped.startswith(self.OPEN):
                    self.state, self.found = "think", True
                    self.buf = stripped[len(self.OPEN):]
                elif self.OPEN.startswith(stripped):  # 可能是被切开的 "<thi"，等下一个片段
                    break
                else:
                    self.state = "text"
            elif self.state == "think":
                i = self.buf.find(self.CLOSE)
                if i >= 0:
                    if i:
                        out.append(("reasoning", self.buf[:i]))
                    self.buf, self.state = self.buf[i + len(self.CLOSE):], "text"
                    continue
                keep = next((k for k in range(len(self.CLOSE) - 1, 0, -1) if self.buf.endswith(self.CLOSE[:k])), 0)
                if len(self.buf) > keep:
                    out.append(("reasoning", self.buf[:len(self.buf) - keep]))
                    self.buf = self.buf[len(self.buf) - keep:]
                break
            else:
                out.append(("text", self.buf))
                self.buf = ""
        return out

    def flush(self) -> list[tuple[str, str]]:
        if not self.buf:
            return []
        kind = "reasoning" if self.state == "think" else "text"
        text, self.buf = self.buf, ""
        return [(kind, text)]
