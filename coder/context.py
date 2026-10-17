"""上下文管理：对话太长时，先裁剪早期的工具输出；还不够，再把早期对话压缩成摘要。

为什么分两步：工具输出（读文件、运行日志）通常占上下文的大头，而且过后可以重新获取，
裁剪它几乎没有信息损失、也不需要额外调用模型；摘要会丢细节，还要多花一次调用，所以放在后面。
"""

import json

IMAGE_TOKENS = 800          # 一张图片大约占用的 token（粗估）
KEEP_RECENT_TOOL_RESULTS = 6  # 最近几条工具结果保持原样
PRUNED_HEAD = 400           # 裁剪后保留的开头字符数
PRUNE_THRESHOLD = 1500      # 超过这个长度的早期工具输出才裁剪
KEEP_RECENT_CALLS = 2       # 最近几条助手消息里的工具参数保持原样
# 写文件类工具的大参数：内容已经落盘，需要时可以重新读取，早期消息里只留占位说明
BULKY_ARGS = {"write_file": ("content",), "edit_file": ("old_string", "new_string")}

SUMMARY_INSTRUCTION = """下面是一段编程助手与用户的对话记录。请写一份摘要，让助手在早期对话被清空后能无缝继续工作。

必须包含：
1. 用户提出的所有要求和偏好（保留关键原话；如果用户发过图片，写清图片里的关键信息，比如题目和示例）
2. 已完成的工作：读过、修改过、新建过的文件路径，以及关键改动
3. 运行过的重要命令和结果（例如测试是否通过、报错信息）
4. 重要的发现和决定（例如 bug 的原因、选择某种实现的理由）
5. 当前进度和还没完成的事项
6. 工作集：继续工作必须知道的规则和接口（例如需求里的具体规则、函数签名、数据格式、边界情况），原样保留，不要概括成"按需求实现"
7. 下一步要做的第一件事

用要点列表，简洁，但不要遗漏文件路径、函数名、错误信息等具体信息。只输出摘要本身。

对话记录：
"""


def estimate_text(text: str) -> int:
    """粗略估算 token 数：英文约 4 个字符一个 token，中文约 1 个字一个 token。"""
    ascii_chars = sum(1 for c in text if ord(c) < 128)
    return ascii_chars // 4 + (len(text) - ascii_chars)


def estimate_message(m: dict) -> int:
    tokens = 4
    content = m.get("content")
    if isinstance(content, list):
        for part in content:
            tokens += IMAGE_TOKENS if part.get("type") == "image_url" else estimate_text(part.get("text", ""))
    elif content:
        tokens += estimate_text(content)
    tokens += estimate_text(m.get("reasoning_content") or "")
    for c in m.get("tool_calls", []):
        tokens += estimate_text(c["function"]["name"] + c["function"]["arguments"])
    return tokens


def estimate_tokens(messages: list[dict]) -> int:
    return sum(estimate_message(m) for m in messages)


def prune_tool_outputs(messages: list[dict], keep_recent: int = KEEP_RECENT_TOOL_RESULTS) -> int:
    """把较早的长工具输出裁剪成开头一小段（原地修改）。返回裁掉的字符数。"""
    tool_indexes = [i for i, m in enumerate(messages) if m["role"] == "tool"]
    removed = 0
    for i in tool_indexes[:len(tool_indexes) - keep_recent]:
        content = messages[i]["content"]
        if len(content) > PRUNE_THRESHOLD:
            messages[i] = {**messages[i], "content": content[:PRUNED_HEAD]
                           + f"\n…（这是较早的工具输出，已省略 {len(content) - PRUNED_HEAD} 个字符；需要的话请重新读取）"}
            removed += len(content) - PRUNED_HEAD
    return removed


def stub_bulky_args(messages: list[dict], keep_recent: int = KEEP_RECENT_CALLS) -> int:
    """把较早的写文件、改文件调用里的大段内容换成占位说明（原地修改）。返回省掉的字符数。

    模型自己写出的文件内容会原样留在助手消息的工具参数里，一次 write_file 可能就有几千 token，
    而这些内容已经在磁盘上了。只改参数里的大字段，调用本身（工具名、路径）保留，消息结构仍然合法。
    """
    indexes = [i for i, m in enumerate(messages) if m["role"] == "assistant" and m.get("tool_calls")]
    removed = 0
    for i in indexes[:max(len(indexes) - keep_recent, 0)]:
        calls = []
        for c in messages[i]["tool_calls"]:
            fields = BULKY_ARGS.get(c["function"]["name"])
            raw = c["function"]["arguments"]
            if fields and len(raw) > PRUNE_THRESHOLD:
                try:
                    args = json.loads(raw)
                except json.JSONDecodeError:
                    args = None
                if isinstance(args, dict):
                    for f in fields:
                        v = args.get(f)
                        if isinstance(v, str) and len(v) > PRUNED_HEAD:
                            args[f] = f"…（较早写入的 {len(v)} 个字符已省略，文件当前内容请用 read_file 查看）"
                    new = json.dumps(args, ensure_ascii=False)
                    if len(new) < len(raw):
                        removed += len(raw) - len(new)
                        c = {**c, "function": {**c["function"], "arguments": new}}
            calls.append(c)
        messages[i] = {**messages[i], "tool_calls": calls}
    return removed


def find_split(messages: list[dict], keep_tokens: int) -> int | None:
    """找一个切分点：之前的消息压缩成摘要，之后的原样保留。

    切分点必须落在 user 或 assistant 消息上：tool 消息必须紧跟着发起调用的 assistant 消息，
    不能把它们拆开。在满足"保留部分不超过 keep_tokens"的前提下，尽量多保留。
    """
    candidates = [i for i in range(2, len(messages)) if messages[i]["role"] in ("user", "assistant")]
    if not candidates:
        return None
    for i in candidates:
        if estimate_tokens(messages[i:]) <= keep_tokens:
            return i
    return candidates[-1]  # 最后一段本身就很长：至少把前面的都压缩掉


def render_transcript(messages: list[dict], max_chars: int) -> str:
    """把消息转成纯文本记录用于生成摘要（不直接发送 tool_calls 结构，兼容性更好）。"""
    lines = []
    for m in messages:
        role = m["role"]
        content = m.get("content")
        if isinstance(content, list):
            text = " ".join(p.get("text", "") if p.get("type") == "text" else "[图片]" for p in content)
        else:
            text = content or ""
        if role == "user":
            lines.append(f"【用户】{text}")
        elif role == "assistant":
            calls = "; ".join(f"{c['function']['name']}({c['function']['arguments'][:300]})"
                              for c in m.get("tool_calls", []))
            lines.append(f"【助手】{text}" + (f"\n  调用工具：{calls}" if calls else ""))
        elif role == "tool":
            lines.append(f"【工具结果】{text[:1500]}")
    out = "\n".join(lines)
    if len(out) > max_chars:  # 记录本身太长：保留头尾（开头有任务要求，结尾是最新进展）
        half = max_chars // 2
        out = out[:half] + "\n…（中间省略）…\n" + out[-half:]
    return out


def summarize(llm, messages: list[dict], max_chars: int):
    """调用模型生成摘要。返回模型的回复对象（含 content 和 usage）。"""
    prompt = SUMMARY_INSTRUCTION + render_transcript(messages, max_chars)
    return llm.chat([{"role": "user", "content": prompt}], tools=[])


def build_compacted(messages: list[dict], split: int, summary: str, facts: str = "") -> list[dict]:
    """[system, 摘要, (确认), 保留的消息...]，保证消息顺序合法。

    facts 是程序记录的确定信息（例如改过哪些文件），直接附在摘要后面，不经过模型转述，不会记错。
    """
    head = [messages[0], {"role": "user", "content":
            "【之前的对话已压缩为以下摘要】\n" + summary
            + (f"\n\n{facts}" if facts else "")
            + "\n\n（以上是早期对话的摘要。文件的当前内容请以实际读取为准。）"}]
    if messages[split]["role"] == "user":
        head.append({"role": "assistant", "content": "好的，我已了解之前的进展。"})
    return head + messages[split:]
