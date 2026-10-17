"""Agent 核心循环：调用模型 → 执行工具 → 把结果喂回模型 → 直到模型不再调用工具。"""
import json
import os
import platform
import threading
from datetime import date

from . import context
from .checkpoints import Checkpoints, agent_note
from .permissions import COMMAND_TOOLS, PermissionManager
from .redact import WRITE_BACK_ERROR, placeholder_in, redact
from .tools import Tool, ToolError
from .workspace import Workspace, WorkspaceError

REPEAT_LIMIT = 3  # 连续这么多次相同的工具调用，就提醒模型换个办法
CYCLE_REPEATS = 3  # 两三个调用组成的循环（A-B-A-B）重复这么多次，也提醒
FAIL_LIMIT = 3     # 同一个调用（同样的参数）失败这么多次，提醒换个办法
MAX_FORMAT_ERRORS = 3  # 连续这么多步的工具调用都格式错误（参数不是 JSON、回复被截断），就停下
MAX_FINISH_NUDGES = 2  # 必须用工具交付时，没交付就想结束，最多提醒几次
MAX_VERIFY_VETOES = 1  # 改了代码没验证就想结束，最多否决几次（之后它说明原因就可以结束）
CODE_SUFFIXES = {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".kt", ".c", ".cc",
                 ".cpp", ".h", ".hpp", ".rb", ".php", ".cs", ".sh", ".swift", ".scala", ".vue", ".svelte"}
BAD_ARGS = ("错误：这次工具调用的参数不是合法的 JSON（可能是内容太长被截断了，或者引号、换行没有转义），没有执行。"
            "请重新调用；内容很长时分成几次（先 write_file 写一部分，再用 edit_file 补充）。")
TRUNCATED_CALL = ("错误：你的回复太长，达到了输出上限被截断，这次的工具调用都没有执行（参数可能不完整）。"
                  "请重新调用，并把回复写短：大文件分几次写，先 write_file 写一部分，再用 edit_file 补充。")
VERIFY_NOTE = ("[你改了代码（{files}），但之后没有成功运行过验证（测试、构建或运行脚本）。请运行合适的命令验证你的改动；"
               "如果确实无法验证（比如项目没有测试、需要外部服务），说明原因后再结束。]")
FINISH_NUDGE = "[你还没有调用 {tool} 交付，不调用不算完成。做完了就调用 {tool}；还没做完就接着做。]"
GRACE_NOTE = ("[步数用完了。这是最后一次机会：现在立刻调用 {tool} 交付，写明做了什么、怎么验证的、还有什么没做完。"
              "不要调用别的工具。]")
FORMAT_STOP = "连续 {n} 步的工具调用都格式错误，任务暂停。可以输入“继续”让它接着做。"
TRUNCATED_NOTE = ("[Your previous reply was cut off because it reached the output length limit, so no tool call was "
                  "sent. Continue the task now. Keep each reply short: think briefly, and write large files in parts "
                  "(write_file a first part, then add the rest with edit_file) instead of one huge call.]")
MAX_TRUNCATIONS = 3  # 同一轮里连续被截断这么多次就停下，避免空转
SUMMARY_GAP = 4   # 两次摘要压缩之间至少间隔这么多次模型调用，防止反复压缩（每次都要多调用一次模型，还会让缓存失效）
COMPACT_TARGET = 0.6  # 压缩后的目标：上下文降到阈值的这个比例以下，留出余量
MAX_REQUEST_CHARS = 4000  # 压缩时原样保留的用户原始要求的最大长度

SYSTEM_PROMPT = """You are a coding agent working inside the user's project directory. \
You complete software engineering tasks by calling tools to explore, edit and run code.

# Environment
- Workspace root: {root}
- OS: {environment}
- Today: {today}

# How to work
1. Explore before acting: use list_dir / grep / read_file to understand the relevant code. \
Never guess file contents.
2. Always read a file before editing it. Prefer edit_file for small changes; use write_file \
only for new files or full rewrites.
3. After changing code, verify it: run the tests, the build, or the script with run_command. \
If it fails, read the error and fix it.
4. Keep changes minimal and match the existing code style. Do not add features the user did not ask for.
5. If a tool returns an error, read it carefully and adjust; do not repeat the same failing call.
6. If the user rejects an action, follow their feedback instead of retrying the same thing.
7. When done, give a short summary of what you changed. If the user only asks a question, wants an explanation, \
or wants a solution (for example an algorithm problem) and does not ask you to change files, answer in the chat \
with the complete code in your reply. You may run a quick script to check your answer, but do not add files to \
the user's project just to answer.
8. The user may attach images, such as screenshots of a coding problem or an error message. Read them carefully and treat their content as part of the task.
9. Language: write every message to the user (including short progress notes between tool calls) \
in the same language as the user's latest message. If the user writes Chinese, reply in Chinese.
{scratch}{project_notes}"""

SCRATCH_NOTE = """
# Scratch mode
The user did not open a project: the workspace root is a temporary scratch directory for this conversation only. \
Answer in the chat and put the complete solution in your reply; files you write here are only for your own testing, \
and the user will not look at them. Never ask the user to choose or create a workspace.
"""

# 项目说明文件：类似 Claude Code 的 CLAUDE.md，放在工作区根目录会自动加载
PROJECT_NOTES_FILE = "AGENT.md"


class Cancelled(Exception):
    """用户从界面上点了停止。"""


def truncate(text: str, limit: int) -> str:
    """保留头尾，截掉中间。报错信息通常在末尾，开头是上下文，所以两头都要。"""
    if len(text) <= limit:
        return text
    half = limit // 2
    return f"{text[:half]}\n\n...（省略了 {len(text) - limit} 个字符）...\n\n{text[-half:]}"


class Agent:
    def __init__(self, llm, tools: dict[str, Tool], workspace: Workspace,
                 permissions: PermissionManager, ui, max_steps: int = 50,
                 max_tool_output: int = 12_000, context_limit: int = 200_000, sandbox=None):
        self.llm = llm
        self.sandbox = sandbox  # 沙箱模式：命令在 Docker 容器里执行（系统提示里的环境说明随之改变）
        self.tools = tools
        self.ws = workspace
        self.permissions = permissions
        self.ui = ui
        self.max_steps = max_steps
        self.max_tool_output = max_tool_output
        self.context_limit = context_limit  # 上下文超过这么多 token 就压缩；0 表示不压缩
        self.tool_schemas = [t.schema() for t in tools.values()]
        self._tool_schema_tokens = context.estimate_text(json.dumps(self.tool_schemas, ensure_ascii=False))
        self._cancel = threading.Event()
        self.usage = {"prompt": 0, "completion": 0, "cached": 0}  # 本次对话累计 token
        self.steps = 0        # 累计调用模型的次数（评测用）
        self.call_log: list[dict] = []  # token 账本：每次调用模型的用量和上下文构成（评测用）
        self.compactions = 0  # 累计压缩上下文的次数
        self._last_prompt: tuple[int, int] | None = None  # (上次请求的实际 token 数, 当时的消息条数)
        self._recent_calls: list[tuple[str, str]] = []
        self._ratio = 1.0          # 实际 token 数 / 估算值，用上次请求校准估算
        self._last_summary_step = -SUMMARY_GAP
        self.touched_files: list[str] = []  # 本次对话里新建或修改过的文件，压缩时原样写进摘要
        self._request = ""         # 本轮用户的原始要求
        self.step_hook = None      # 每步工具执行完后调用，返回的文字附在最后一条工具结果后面（团队模式推送黑板更新）
        self.facts_hook = None     # 压缩上下文时调用，返回的文字原样写进摘要（团队模式的项目记忆总览）
        self.checkpoints = Checkpoints(workspace.root)  # 每轮一个检查点，可以撤销这一轮的文件修改
        self.checkpoint_turns = True  # 团队模式里由 Team 按轮建检查点，各个 agent 只往里记
        self._pending_note = ""    # 下一轮开头告诉模型的事：用户撤销了修改、服务重启打断了团队任务等
        self.redact = os.getenv("CODER_REDACT", "1") != "0"  # 遮蔽工具结果里的密钥（见 redact.py）
        self.scratch = False  # 临时工作区（用户没有选项目，只是来问问题）：在聊天里给出完整答案
        self.verify_on_stop = os.getenv("CODER_VERIFY_ON_STOP", "1") != "0"  # 改了代码没验证就想结束时否决一次
        self.finish_tool: str | None = None  # 必须用这个工具交付才算完成（团队的子 agent：complete_task）
        self.finished = False      # 这一轮已经用 finish_tool 交付了
        self.finish_hook = None    # 想结束时调用，返回的文字作为新消息继续（团队的主 agent：等子 agent 的结果）
        self._inbox: list[str] = []  # 运行中用户插的话，下一步之前插入对话
        self._inbox_lock = threading.Lock()
        self._dirty: list[str] = []  # 这一轮改过、之后还没有成功验证过的代码文件
        self._vetoes = self._nudges = self._format_errors = 0
        self._failures: dict[tuple[str, str], int] = {}  # (工具, 参数) -> 这一轮失败了几次
        self.reset()

    def set_scratch(self, scratch: bool, extra_prompt: str = "") -> None:
        """标记为临时工作区，重新生成系统提示（extra_prompt：团队模式的主 agent 追加在后面的说明）。"""
        self.scratch = scratch
        self.messages[0]["content"] = self._system_prompt() + extra_prompt

    def add_tools(self, tools: dict[str, Tool]) -> None:
        """追加工具（比如启动完成的 MCP 服务器提供的），同时更新发给模型的工具定义和上下文估算。"""
        self.tools.update(tools)
        self.tool_schemas = [t.schema() for t in self.tools.values()]
        self._tool_schema_tokens = context.estimate_text(json.dumps(self.tool_schemas, ensure_ascii=False))

    def undo(self, force: bool = False) -> dict:
        """撤销最近一轮的文件修改（见 checkpoints.py），下一轮告诉模型。"""
        result = self.checkpoints.undo(force)
        if result["restored"] or result["deleted"]:
            self._pending_note = agent_note(result)
        return result

    def steer(self, text: str) -> None:
        """运行中用户插话：排队，在当前这步工具执行完后插入对话（不打断正在进行的调用）。"""
        with self._inbox_lock:
            self._inbox.append(text)

    def _drain_inbox(self) -> str:
        with self._inbox_lock:
            items, self._inbox = self._inbox, []
        if not items:
            return ""
        return "[用户在你工作时补充：]\n" + "\n".join(items)

    def mark_finished(self) -> None:
        """finish_tool 交付成功（由交付工具调用）。"""
        self.finished = True

    def cancel(self) -> None:
        """请求停止当前任务。在下一次调用模型或执行工具之前生效。"""
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def _check_cancel(self) -> None:
        if self._cancel.is_set():
            raise Cancelled()

    def reset(self) -> None:
        self.messages: list[dict] = [{"role": "system", "content": self._system_prompt()}]
        self._last_prompt = None
        self._recent_calls = []

    def _system_prompt(self) -> str:
        notes = ""
        notes_path = self.ws.root / PROJECT_NOTES_FILE
        if notes_path.is_file():
            notes = f"\n# Project instructions ({PROJECT_NOTES_FILE})\n" + notes_path.read_text("utf-8")
        if self.sandbox:
            from .sandbox import ENVIRONMENT
            environment = ENVIRONMENT
        else:
            is_windows = platform.system() == "Windows"
            shell = "cmd.exe (use Windows commands, e.g. dir, type)" if is_windows else "/bin/sh"
            environment = f"{platform.system()}; commands run via {shell}"
        return SYSTEM_PROMPT.format(
            root=self.ws.root,
            environment=environment,
            today=date.today().isoformat(),
            scratch=SCRATCH_NOTE if self.scratch else "",
            project_notes=notes,
        )

    def run(self, user_input: str, images: list[str] | None = None) -> None:
        """执行一轮任务。images 是 data URL 格式的图片（比如题目截图），会和文字一起发给模型。"""
        self._cancel.clear()
        # 思考内容只在同一轮工具调用中需要回传；开始新一轮时丢掉旧的，节省 token
        for m in self.messages:
            m.pop("reasoning_content", None)
        if self.checkpoint_turns:
            self.checkpoints.begin(user_input)
        text = f"{self._pending_note}\n\n{user_input}" if self._pending_note else user_input
        self._pending_note = ""
        self.messages.append({"role": "user", "content": self._user_content(text, images)})
        self._request = user_input
        self._recent_calls = []
        self._dirty, self._failures = [], {}
        self._vetoes = self._nudges = self._format_errors = 0
        self.finished = False
        truncations = 0
        for _ in range(self.max_steps):
            self._check_cancel()
            news = self._drain_inbox()
            if news:  # 用户插话：当前这步的工具执行完了，在下一次调用模型之前插入
                self.messages.append({"role": "user", "content": news})
            self._maybe_compact()
            sent = len(self.messages)
            composition = self._composition()
            estimate = sum(composition.values())
            msg = self.llm.chat(self.messages, self.tool_schemas, on_delta=self._on_delta)
            self.steps += 1
            usage = getattr(msg, "usage", None)
            self._add_usage(usage)
            if usage:
                self._last_prompt = (usage.prompt, sent)
                if estimate:
                    self._ratio = max(1.0, usage.prompt / estimate)
                self.call_log.append({"step": self.steps, "prompt": usage.prompt, "cached": getattr(usage, "cached", 0),
                                      "completion": usage.completion, "messages": sent, "composition": composition,
                                      "finish": getattr(msg, "finish_reason", None)})  # length = 被输出上限截断
            assistant, bad = self._assistant_message(msg)
            self.messages.append(assistant)
            reasoning = getattr(msg, "reasoning_content", None)
            if msg.content or reasoning:
                self.ui.assistant(msg.content or "", reasoning)
            truncated = getattr(msg, "finish_reason", None) == "length"
            if not msg.tool_calls:
                # 回复太长被截断（达到输出上限）时工具调用发不出来，不能当成完成：告诉模型继续，并把回复写短
                if truncated and truncations < MAX_TRUNCATIONS:
                    truncations += 1
                    self.ui.warn("模型的回复太长被截断了，提醒它继续")
                    self.messages.append({"role": "user", "content": TRUNCATED_NOTE})
                    continue
                follow = self._before_finish()
                if follow:  # 还不能结束：有新插话 / 子 agent 还在跑 / 没有交付 / 改了代码没验证
                    self.messages.append({"role": "user", "content": follow})
                    continue
                return  # 模型不再调用工具 = 任务完成
            truncations = 0
            if truncated:
                self.ui.warn("模型的回复太长被截断了，这次的工具调用没有执行")
            # 连续几步都是格式错误（参数不是 JSON、回复被截断）：模型在空转，停下
            broken = truncated or all(c.id in bad for c in msg.tool_calls)
            self._format_errors = self._format_errors + 1 if broken else 0
            for call in msg.tool_calls:
                self._check_cancel()  # 中断后由 interrupt() 补齐未执行的工具结果
                if truncated:
                    result = TRUNCATED_CALL
                elif call.id in bad:
                    result = BAD_ARGS
                    self.ui.tool_result(result)
                else:
                    result = self._execute(call.function.name, call.function.arguments)
                result += self._repeat_warning(call.function.name, call.function.arguments, result)
                self.messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
            if self.finish_tool and self.finished:
                return  # 已经交付：不再多调用一次模型
            if self.step_hook:
                news = self.step_hook()
                if news:
                    self.messages[-1]["content"] += news
            if self._format_errors >= MAX_FORMAT_ERRORS:
                self.ui.warn(FORMAT_STOP.format(n=self._format_errors))
                return
        if self.finish_tool and not self.finished:
            self._grace_turn()
            if self.finished:
                return
        self.ui.warn(f"已达到最大步数 {self.max_steps}，任务暂停。可以输入“继续”让它接着做。")

    def _before_finish(self) -> str:
        """模型想结束时：返回非空文字表示还不能结束，这段文字作为新消息让它继续。"""
        news = self._drain_inbox()
        if news:  # 想结束时用户刚好插话：先处理
            return news
        if self.finish_hook:
            follow = self.finish_hook()
            if follow:
                return follow
        if self.finish_tool and not self.finished:
            if self._nudges < MAX_FINISH_NUDGES:
                self._nudges += 1
                return FINISH_NUDGE.format(tool=self.finish_tool)
            return ""
        if self.verify_on_stop and self._dirty and self._vetoes < MAX_VERIFY_VETOES:
            self._vetoes += 1
            self.ui.info("改了代码但还没有验证，提醒它先验证")
            return VERIFY_NOTE.format(files="、".join(self._dirty[:8]) + (" 等" if len(self._dirty) > 8 else ""))
        return ""

    def _grace_turn(self) -> None:
        """步数用完还没交付：最后一次机会，只提供交付工具（参考 Gemini CLI 子 agent 的收尾回合）。"""
        schemas = [s for s in self.tool_schemas if s["function"]["name"] == self.finish_tool]
        if not schemas:
            return
        self._check_cancel()
        self.messages.append({"role": "user", "content": GRACE_NOTE.format(tool=self.finish_tool)})
        msg = self.llm.chat(self.messages, schemas, on_delta=self._on_delta)
        self.steps += 1
        self._add_usage(getattr(msg, "usage", None))
        assistant, bad = self._assistant_message(msg)
        self.messages.append(assistant)
        if msg.content:
            self.ui.assistant(msg.content, getattr(msg, "reasoning_content", None))
        for call in msg.tool_calls or []:
            if call.function.name == self.finish_tool and call.id not in bad and not self.finished:
                result = self._execute(call.function.name, call.function.arguments)
            else:
                result = f"错误：现在只能调用 {self.finish_tool}"
            self.messages.append({"role": "tool", "tool_call_id": call.id, "content": result})

    @staticmethod
    def _user_content(text: str, images: list[str] | None):
        """没有图片时 content 是字符串；有图片时按 OpenAI 多模态格式拼成列表。"""
        if not images:
            return text
        return [{"type": "text", "text": text}] + [
            {"type": "image_url", "image_url": {"url": url}} for url in images]

    def _on_delta(self, kind: str, text: str) -> None:
        """流式输出的每个片段都会经过这里：检查停止标志，并推给界面。"""
        self._check_cancel()  # 生成过程中点停止，立即中断
        delta = getattr(self.ui, "delta", None)
        if delta and text:  # 空片段只是让我们有机会检查停止标志（比如等待重试时），不推给界面
            delta(kind, text)

    def _add_usage(self, usage) -> None:
        if usage:
            self.usage["prompt"] += usage.prompt
            self.usage["completion"] += usage.completion
            self.usage["cached"] += usage.cached

    def _composition(self) -> dict:
        """估算这次请求的上下文由哪些部分组成（token 数），用来分析钱花在了哪里。"""
        parts = {"system": 0, "tools": self._tool_schema_tokens, "user": 0, "assistant": 0, "tool_results": 0}
        for m in self.messages:
            key = {"system": "system", "user": "user", "assistant": "assistant", "tool": "tool_results"}[m["role"]]
            parts[key] += context.estimate_message(m)
        return parts

    # ---------- 上下文管理 ----------

    def context_tokens(self) -> int:
        """估算下一次请求的 token 数：上次请求的实际值 + 之后新增消息的估算值。"""
        if self._last_prompt and self._last_prompt[1] <= len(self.messages):
            tokens, count = self._last_prompt
            return tokens + context.estimate_tokens(self.messages[count:])
        return context.estimate_tokens(self.messages)

    def _estimate(self) -> int:
        """估算整个请求的 token 数：消息 + 工具定义（固定开销），并用上次请求的实际值校准。"""
        return int((context.estimate_tokens(self.messages) + self._tool_schema_tokens) * self._ratio)

    def _maybe_compact(self) -> None:
        if not self.context_limit or self.context_tokens() < self.context_limit:
            return
        before = self.context_tokens()
        target = int(self.context_limit * COMPACT_TARGET)
        # 第一步：无损裁剪。早期的长工具输出、早期写文件的大段内容，都能重新读取
        context.stub_bulky_args(self.messages)
        context.prune_tool_outputs(self.messages)
        self._last_prompt = None
        # 第二步：还是太长，压缩成摘要。刚压缩过就不再压缩，避免反复压缩
        if self._estimate() >= target and self.steps - self._last_summary_step >= SUMMARY_GAP:
            self.compact()
        # 第三步：还没降到目标以下，就一次裁到底（只保留最新一条工具输出原样）。
        # 必须一次降到明显低于阈值：如果只降到阈值附近，下一步一涨又会触发，每次裁剪都改动前面的消息，
        # 模型服务商的缓存前缀每一步都被打破，输入几乎全部按未命中计费
        if self._estimate() >= target:
            context.stub_bulky_args(self.messages, keep_recent=0)
            context.prune_tool_outputs(self.messages, keep_recent=1)
        self.ui.info(f"上下文较长，已自动压缩：约 {before:,} → {self._estimate():,} tokens")

    def compact(self) -> bool:
        """把早期对话压缩成摘要，只保留最近的部分。返回是否真的压缩了。"""
        limit = self.context_limit or 200_000
        overhead = self._tool_schema_tokens + context.estimate_message(self.messages[0])
        keep = max(int((limit * COMPACT_TARGET - overhead) * 0.5 / self._ratio), 500)
        split = context.find_split(self.messages, keep_tokens=keep)
        if split is None:
            return False
        reply = context.summarize(self.llm, self.messages[1:split], max_chars=limit * 2)
        self._add_usage(getattr(reply, "usage", None))
        if not reply.content:
            return False
        self._last_summary_step = self.steps
        self.messages = context.build_compacted(self.messages, split, reply.content, self._facts(split))
        self._last_prompt = None
        self.compactions += 1
        return True

    def _facts(self, split: int) -> str:
        """压缩时由程序直接写进摘要的确定信息：用户原始要求的原文、改过的文件。"""
        parts = []
        kept = any(m["role"] == "user" and self._request and self._request in str(m.get("content"))
                   for m in self.messages[split:])
        if self._request and not kept:
            req = self._request
            if len(req) > MAX_REQUEST_CHARS:
                req = req[:MAX_REQUEST_CHARS] + "…（后面省略，需要的话请向用户确认）"
            parts.append("【用户本轮的原始要求（原文）】\n" + req)
        if self.touched_files:
            parts.append("【本次对话中新建或修改过的文件】" + "、".join(self.touched_files))
        if self.facts_hook:  # 团队模式的主 agent：项目记忆总览（程序维护，不经过模型转述）
            parts.append("【项目记忆】\n" + self.facts_hook())
        return "\n\n".join(parts)

    def _repeat_warning(self, name: str, raw_args: str, result: str = "") -> str:
        """陷入循环的几种迹象（参考 Gemini CLI、OpenHands 的卡住检测），提醒模型换个办法：
        连续多次完全相同的调用；两三个调用组成的循环反复出现（A-B-A-B）；同一个调用反复失败。"""
        key = (name, raw_args)
        self._recent_calls = (self._recent_calls + [key])[-3 * CYCLE_REPEATS:]
        recent, notes = self._recent_calls, []
        if len(recent) >= REPEAT_LIMIT and len(set(recent[-REPEAT_LIMIT:])) == 1:
            notes.append(f"你已经连续 {REPEAT_LIMIT} 次用完全相同的参数调用 {name}，"
                         "结果不会改变。请换一种方法，或者向用户说明遇到的困难。")
        else:
            for size in (2, 3):
                tail = recent[-size * CYCLE_REPEATS:]
                if (len(tail) == size * CYCLE_REPEATS and len(set(tail[:size])) == size
                        and all(tail[i] == tail[i % size] for i in range(len(tail)))):
                    names = " → ".join(n for n, _ in tail[:size])
                    notes.append(f"你在重复同一组操作（{names}），已经重复 {CYCLE_REPEATS} 次，结果没有变化。"
                                 "请停下来想想问题出在哪里，换一种方法。")
                    break
        if result.startswith("错误"):  # 失败次数照常累计（和上面的循环提醒互不影响）
            self._failures[key] = self._failures.get(key, 0) + 1
            if self._failures[key] == FAIL_LIMIT:
                notes.append(f"这个 {name} 调用（同样的参数）已经失败了 {FAIL_LIMIT} 次。"
                             "不要再原样重试：先弄清楚失败的原因，或者换一种方法。")
        return "".join(f"\n\n[提醒] {n}" for n in notes)

    def _execute(self, name: str, raw_args: str) -> str:
        """执行一次工具调用。所有错误都转成文字返回给模型，而不是让程序崩溃。"""
        tool = self.tools.get(name)
        if tool is None:
            return f"错误：不存在工具 {name}，可用工具：{', '.join(self.tools)}"
        try:
            args = json.loads(raw_args or "{}")
        except json.JSONDecodeError as e:
            return f"错误：工具参数不是合法的 JSON（{e}），请重新生成"
        self.ui.tool_call(name, args)
        try:
            if name in ("write_file", "edit_file") and placeholder_in(args):
                raise ToolError(WRITE_BACK_ERROR)  # 写回占位符会把真正的密钥覆盖掉
            if tool.needs_permission:
                preview = tool.preview(**args)  # 先预检，参数有问题就不用打扰用户
                command = args.get("command") if name in COMMAND_TOOLS else None
                network = bool(args.get("network")) if name in COMMAND_TOOLS else False
                allowed, feedback = (self.permissions.check(name, preview, command=command, network=True) if network
                                     else self.permissions.check(name, preview, command=command))
                if not allowed:
                    result = "用户拒绝了这个操作。"
                    if feedback:
                        result += f"用户反馈：{feedback}"
                    self.ui.tool_result(result)
                    return result
            path = args.get("path") if name in ("write_file", "edit_file") else None
            target = self.ws.resolve(path) if isinstance(path, str) else None
            if target:
                self.checkpoints.before_write(target)
            result = tool.run(**args)
            if target:
                self.checkpoints.after_write(target)
                if path not in self.touched_files:
                    self.touched_files.append(path)
                if target.suffix.lower() in CODE_SUFFIXES and path not in self._dirty:
                    self._dirty.append(path)  # 改了代码：之后要成功运行一次验证
            if name in COMMAND_TOOLS and str(result).startswith("退出码：0"):
                self._dirty = []  # 改动之后成功运行过命令（测试、构建、脚本）：算验证过了
        except (ToolError, WorkspaceError) as e:
            result = f"错误：{e}"
        except TypeError as e:  # 模型传了不存在的参数或缺参数
            result = f"错误：参数不正确（{e}）"
        except Exception as e:
            result = f"错误：{type(e).__name__}: {e}"
        if self.redact:  # 密钥不发给模型，也不显示、不存进对话记录
            result, _ = redact(result)
        result = truncate(result, self.max_tool_output)
        self.ui.tool_result(result)
        return result

    @staticmethod
    def _assistant_message(msg) -> tuple[dict, set[str]]:
        """把 SDK 返回的对象转成可以再发给 API 的 dict，返回 (消息, 参数不合法的工具调用 id)。

        参数不是合法 JSON 对象的调用，发回历史时换成合法的空参数：带着不合法参数的对话，下一次调用会被
        服务商整个拒绝（400 "function.arguments must be valid JSON"），任务直接失败。"""
        raw = getattr(msg, "raw_content", None)  # 思考过程写在正文里的模型：原样发回
        d: dict = {"role": "assistant", "content": raw if raw is not None else (msg.content or "")}
        if raw is None and getattr(msg, "reasoning_content", None):
            d["reasoning_content"] = msg.reasoning_content
        bad: set[str] = set()
        if msg.tool_calls:
            calls = []
            for c in msg.tool_calls:
                args = c.function.arguments or "{}"
                try:
                    ok = isinstance(json.loads(args), dict)
                except json.JSONDecodeError:
                    ok = False
                if not ok:
                    bad.add(c.id)
                    args = "{}"
                calls.append({"id": c.id, "type": "function", "function": {"name": c.function.name, "arguments": args}})
            d["tool_calls"] = calls
        return d, bad

    def interrupt(self) -> None:
        """用户按 Ctrl+C 中断后修复历史：API 要求每个 tool_call 都必须有对应的 tool 结果。"""
        for i in range(len(self.messages) - 1, -1, -1):
            m = self.messages[i]
            if m["role"] != "assistant":
                continue
            answered = {x["tool_call_id"] for x in self.messages[i + 1:] if x["role"] == "tool"}
            for c in m.get("tool_calls", []):
                if c["id"] not in answered:
                    self.messages.append({"role": "tool", "tool_call_id": c["id"],
                                          "content": "用户中断了执行"})
            return
