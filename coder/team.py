"""团队模式：主 agent 统筹，子 agent 分头完成模块，通过共享黑板互通。

分工：
- 主 agent（lead）：读懂全局，先把需求写成验收测试，再拆分任务、定好模块之间的接口契约，派给子 agent；
  子 agent 交回后运行验收测试，把失败的部分带着具体意见派回去返工，直到通过。
- 子 agent：各自只负责一部分文件（写别人的文件会被拒绝），在自己的上下文里完成并自测，交回简短汇报。
  每个子 agent 的上下文只装自己那部分代码，不会因为整个项目太大而频繁压缩。

子 agent 之间不能直接对话，靠共享黑板保持一致（借鉴 LangGraph 的中央 state）：
- 契约（contracts）：模块之间的接口约定。单写者：只有契约的负责人能修改，其他人只能提问
- 决策日志（decisions）：只追加，记录"我这样实现了某某"，避免两边各做一套
- 留言（messages）：给某个任务或主 agent 的问题和通知
- 任务看板（tasks）：谁负责什么、什么状态
每个 agent 每一步调用模型之前，黑板上新出现的、和它相关的内容会自动附在工具结果后面，不需要它主动去查。
"""
import fnmatch
import threading
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

from pathlib import Path

from .agent import Agent, Cancelled
from .memory import ProjectMemory
from .team_roles import MAX_PER_QUALITY_ROLE, QUALITY_ROLES, ROLES, role_guide
from .permissions import PermissionManager
from .checkpoints import Checkpoints
from .redact import redact
from .tools import ProcessManager, Tool, ToolError, build_tools
from .tools.fs import MAX_FILE_BYTES, is_binary, read_text
from .workspace import Workspace, WorkspaceError

NL = chr(10)

LEAD = "lead"
SUB_MAX_STEPS = 40
MAX_PARALLEL = 4
MAX_COMPLETE_REJECTS = 3  # complete_task 最多提交几次：前几次检查不通过退回，最后一次照收（在汇报里注明）
WAIT_SLICE = 0.5          # 等子 agent 时每隔多久检查一次停止标志（秒）
REPORT_CHARS = 1500  # 子 agent 汇报交给主 agent 时的最大长度
PRELOAD_CHARS = 80_000  # 一开始直接交给子 agent 的文件内容最多这么多字符，超出的列出路径让它自己读
# 什么时候拆分：auto 由主 agent 判断（小任务自己做）；always 必须拆分（用于对比实验）
WHEN = {
    "auto": "Delegating costs a lot: every sub-agent re-reads the spec and code, and coordination adds rounds. "
            "Do the task yourself whenever you can hold the spec and the code you write in your own context "
            "(roughly: under ~100k tokens of spec + code, or under ~4000 lines of new code), even if it has "
            "several modules; even then, in team mode you must still plan and dispatch a `tester` task and a "
            "`security` task at the end to verify and review your code. Delegate the implementation only when the "
            "job is clearly bigger than that, and then work like this:",
    "always": "This task must be delegated: sub-agents implement the modules and write the acceptance tests; "
              "you design the split and the contracts, coordinate, and integrate. Work like this:",
}

LEAD_PROMPT = """

# Team mode: you are the lead
You can delegate work to sub-agents. Each sub-agent has its own fresh context, sees only the task you give it, \
and can only write the files you assign to it. They share a blackboard with you (contracts, decisions, messages).

{roles}

# Project memory
A large project does not fit in your context, so keep the big picture in the project memory, not in your context:
- index_docs(paths) splits requirement documents into numbered sections (S1, S2, ...) and returns the outline.
- memory() shows the outline, the contracts, the task board, and a card for every code file (its interface and \
dependencies, extracted from the code). Call it whenever you need the big picture, and right after your context \
has been compacted, instead of re-reading the whole project.
- Read details only when you need them: spec_section(ids) for requirement text, read_file for code.

{when}
1. Explore, call index_docs on the requirement documents, and read the spec once to understand the whole picture.
2. Design the module split and write precise interface contracts (signatures, data formats, error behaviour). \
Shared base code that every module imports (errors, tiny helpers) you may write yourself.
3. Call plan_tasks. Every task has a `role` (see Roles). For each implementation task give: the files it owns, \
its dependencies, `spec_sections` (the sections it implements; their full text is handed to the sub-agent), and \
in `context` only existing files it must change or read in full (the modules it depends on are handed to it as \
interface cards automatically). Tester tasks own tests/acceptance/test_<name>.py and write the acceptance tests \
from their spec sections; make each implementation task depend on the tester task covering it, so the \
implementer can verify against the tests (implementers cannot modify acceptance tests). Security tasks own no \
files (`files: []`) and depend on the implementation tasks they review.
4. Call dispatch with the tasks that are ready. dispatch returns immediately and the sub-agents run in parallel in \
the background. Each report is delivered to you as soon as that task finishes, so dispatch dependent tasks as soon \
as their dependencies are done. Meanwhile you may answer questions on the board or do other work, but never edit \
files owned by a running task. When you have nothing else to do, end your reply without a tool call: the system \
waits for the next sub-agent to finish and hands you its report.
5. When the implementation is done, run the whole acceptance suite yourself with compact output \
(`python -m pytest tests/acceptance -q --tb=line`) and dispatch the security task(s). Send each failure and each \
high or medium security finding to the owning task as concrete feedback; when it is unclear whether the code or \
the test is wrong, read the spec section, or send the failing tests to the tester task to investigate. \
Re-dispatch security only to re-check findings that were fixed. Fix small cross-module glue yourself.
6. Finish only when the tests pass, then summarize.
"""

SUB_PROMPT = """You are a sub-agent in a team, working on one task of a larger job.

# Overall goal (from the lead)
{goal}

# Your task: {task_id}
{description}

# Your role: {role_name}
{role_duty}

# Files you own (you can only create/modify these)
{files}

# Contracts between modules (follow them exactly)
{contracts}

# Decisions and messages from teammates so far
{notes}

# Requirement sections for your task (full text)
{spec}

# Interfaces of the modules you depend on (extracted from their code)
{cards}

# Files the lead gave you (their current content; you have already read them)
{preloaded}

# Rules
- The files above are already loaded: do not read them again unless they may have changed. Read any other code \
you depend on before writing; never guess other modules' interfaces, use the contracts.
- Verify your work by running the acceptance tests that cover your modules (and a quick script if needed). \
Do not write your own test suites: at most a few focused tests for behaviour the acceptance tests do not cover. \
If an acceptance test seems to contradict the spec, tell the lead instead of working around it.
- Run tests with compact output (`-q --tb=short`) so failure logs do not flood your context.
- Do not modify acceptance tests or files you do not own. If you need a change elsewhere or find a contract \
problem, use board_post to tell the lead (to="lead") or the owning task, make a reasonable assumption, \
and record it as a decision.
- Start every module you write with a one-line docstring saying what it does: the lead sees it in the \
module card instead of reading your code. Use spec_section to read other requirement sections if needed.
- Record important implementation choices other modules may depend on with board_post(kind="decision").

# How to deliver
When you are done, call complete_task: summary (what you did, files changed), verification (the commands you ran \
and their results; if you could not verify, say why), open_issues. Your work only counts once complete_task \
accepts it. The system checks that your files exist, that Python files compile, and that you verified your code \
after the last change; if a check fails it tells you what to fix, then call complete_task again.
"""


def _match(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, p) or path == p.rstrip("/") or path.startswith(p.rstrip("/") + "/")
               for p in patterns)


class Blackboard:
    """线程安全的共享状态。每条变化都带递增的版本号，用于给每个 agent 推送增量。"""

    def __init__(self, on_change=None):
        self.lock = threading.RLock()  # 可重入：变化时要在锁内生成快照写进记忆
        self.on_change = on_change     # 每次变化后调用，参数是 to_dict() 的结果（写进项目记忆）
        self.goal = ""
        self.contracts: dict[str, dict] = {}  # 名字 -> {owner, text}
        self.tasks: dict[str, dict] = {}      # id -> {description, files, depends, status, report}
        self.events: list[dict] = []          # 所有变化，按版本号排序

    def _event(self, kind: str, author: str, text: str, to: str = "all") -> None:
        self.events.append({"v": len(self.events) + 1, "kind": kind, "author": author, "to": to, "text": text})
        self.changed()

    def changed(self) -> None:
        if self.on_change:
            self.on_change(self.to_dict())

    def set_contract(self, author: str, name: str, text: str) -> None:
        with self.lock:
            cur = self.contracts.get(name)
            if cur and author not in (cur["owner"], LEAD):
                raise ToolError(f"契约 {name} 由 {cur['owner']} 负责，只有它能修改。"
                                f"请用 board_post 给 {cur['owner']} 留言说明需要的改动。")
            owner = cur["owner"] if cur else author
            self.contracts[name] = {"owner": owner, "text": text}
            self._event("contract", author, f"{'更新' if cur else '新增'}契约 {name}：{text}")

    def post(self, author: str, kind: str, text: str, to: str = "all") -> None:
        with self.lock:
            self._event(kind, author, text, to)

    def set_status(self, task_id: str, status: str, report: str = "") -> None:
        with self.lock:
            self.tasks[task_id]["status"] = status
            if report:
                self.tasks[task_id]["report"] = report
            self._event("status", task_id, f"任务 {task_id}：{status}")

    def digest(self, reader: str, since: int) -> tuple[str, int]:
        """reader 自 since 版本之后需要知道的新内容。返回 (文字, 最新版本号)。"""
        with self.lock:
            new = [e for e in self.events[since:] if e["author"] != reader and e["to"] in ("all", reader)]
            if reader != LEAD:  # 子 agent 不需要每个任务的状态变化
                new = [e for e in new if e["kind"] != "status"]
            lines = [f"- [{e['kind']}] {e['author']}"
                     + (f" → {e['to']}" if e["to"] != "all" else "") + f"：{e['text']}" for e in new]
            return "\n".join(lines), len(self.events)

    def notes_for(self, reader: str) -> str:
        """已有的决策和留言，写进新派出的子 agent 的任务说明。"""
        with self.lock:
            notes = [e for e in self.events if e["kind"] in ("decision", "question", "note")
                     and e["author"] != reader and e["to"] in ("all", reader)]
            return "\n".join(f"- [{e['kind']}] {e['author']}: {e['text']}" for e in notes) or "(none)"

    def snapshot(self) -> str:
        with self.lock:
            out = [f"# 目标\n{self.goal}", "# 契约"]
            out += [f"- {n}（负责：{c['owner']}）：{c['text']}" for n, c in self.contracts.items()] or ["（无）"]
            out.append("# 任务")
            out += [f"- {i} [{t['status']}] 文件：{', '.join(t['files'])}" for i, t in self.tasks.items()] or ["（无）"]
            notes = [e for e in self.events if e["kind"] in ("decision", "question", "note")]
            out.append("# 决策与留言")
            out += [f"- [{e['kind']}] {e['author']} → {e['to']}：{e['text']}" for e in notes] or ["（无）"]
            return "\n".join(out)

    def to_dict(self) -> dict:
        with self.lock:
            return {"goal": self.goal, "contracts": self.contracts, "tasks": self.tasks, "events": self.events}


class SharedPermissions(PermissionManager):
    """团队里所有 agent 共用一份权限设置：界面上切换自动模式、选"总是允许"，对每个 agent 都立即生效。
    询问用户时加锁，多个子 agent 同时请求确认会逐个弹出。"""

    def __init__(self, base: PermissionManager, ask):
        self.base, self.ask = base, ask

    @property
    def auto(self) -> bool:
        return self.base.auto

    @property
    def always_allowed(self) -> set[str]:
        return self.base.always_allowed

    @property
    def allowed_prefixes(self) -> list[str]:
        return self.base.allowed_prefixes

    @property
    def network_allowed(self) -> bool:
        return self.base.network_allowed

    @network_allowed.setter
    def network_allowed(self, value: bool) -> None:
        self.base.network_allowed = value

    def allow_prefix(self, prefix: str) -> None:
        self.base.allow_prefix(prefix)

    def remove_prefix(self, prefix: str) -> None:
        self.base.remove_prefix(prefix)


class BoardRead(Tool):
    name = "board_read"
    description = "查看共享黑板的全部内容：目标、接口契约、任务状态、所有决策和留言。"

    def __init__(self, workspace, board: Blackboard):
        super().__init__(workspace)
        self.board = board

    def run(self) -> str:
        return self.board.snapshot()


class BoardPost(Tool):
    name = "board_post"
    description = ("在共享黑板上发布：decision = 记录你的实现决定（其他模块可能依赖它）；"
                   "question = 向主 agent 或其他任务提问；note = 通知。")
    parameters = {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["decision", "question", "note"]},
            "text": {"type": "string"},
            "to": {"type": "string", "description": "接收者：lead、某个任务 id，或 all（默认）"},
        },
        "required": ["kind", "text"],
    }

    def __init__(self, workspace, board: Blackboard, author: str):
        super().__init__(workspace)
        self.board, self.author = board, author

    def run(self, kind: str, text: str, to: str = "all") -> str:
        self.board.post(self.author, kind, text, to or "all")
        return "已发布到黑板"


class BoardContract(Tool):
    name = "board_contract"
    description = "新增或修改一份接口契约（函数签名、数据格式、错误处理）。只有契约的负责人能修改已有契约。"
    parameters = {
        "type": "object",
        "properties": {"name": {"type": "string"}, "text": {"type": "string"}},
        "required": ["name", "text"],
    }

    def __init__(self, workspace, board: Blackboard, author: str):
        super().__init__(workspace)
        self.board, self.author = board, author

    def run(self, name: str, text: str) -> str:
        self.board.set_contract(self.author, name, text)
        return f"契约 {name} 已更新"


class Guarded(Tool):
    """包装写文件、改文件、运行命令：检查文件归属，并把成功的操作按时间顺序记进团队的操作日志。"""

    def __init__(self, inner: Tool, team: "Team", agent_id: str, owned: list[str] | None):
        super().__init__(inner.ws)
        self.inner, self.team, self.agent_id, self.owned = inner, team, agent_id, owned
        self.name, self.description = inner.name, inner.description
        self.parameters, self.needs_permission = inner.parameters, inner.needs_permission

    def _check(self, kwargs: dict) -> None:
        if "path" not in kwargs or self.name == "run_command":
            return
        rel = self.ws.rel(self.ws.resolve(kwargs["path"]))
        if self.owned is None:  # 主 agent：可以写任何文件，但不能改正在运行的子任务负责的文件
            owner = self.team.owner_of(rel)
            if owner and owner in self.team.running():
                raise ToolError(f"{rel} 由正在运行的任务 {owner} 负责，现在不能改。"
                                "等它交回后再改，或者用 board_post 告诉它需要的改动。")
            return
        if not _match(rel, self.owned):
            owner = self.team.owner_of(rel)
            raise ToolError(f"{rel} 不归你负责（你负责：{', '.join(self.owned)}）。"
                            + (f"它属于 {owner}，" if owner else "")
                            + "如需修改，请用 board_post 告诉负责人或 lead，并先按合理的假设继续你的部分。")

    def preview(self, **kwargs) -> str:
        self._check(kwargs)
        return self.inner.preview(**kwargs)

    def run(self, **kwargs) -> str:
        self._check(kwargs)
        result = self.inner.run(**kwargs)
        self.team.log_op(self.agent_id, self.name, kwargs, result)
        return result


class CompleteTask(Tool):
    name = "complete_task"
    description = ("完成任务后调用，把成果交给主 agent。系统会检查：负责的文件在不在、Python 文件能不能编译、"
                   "改了代码之后有没有成功验证过。不通过会告诉你哪里要改，改好再调用；不调用不算完成。")
    parameters = {
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "做了什么、改了哪些文件"},
            "verification": {"type": "string", "description": "怎么验证的：运行了哪些命令、结果如何；没法验证的说明原因"},
            "open_issues": {"type": "string", "description": "还没解决的问题、需要主 agent 或别的任务处理的事"},
        },
        "required": ["summary", "verification"],
    }

    def __init__(self, workspace, team: "Team", agent_id: str):
        super().__init__(workspace)
        self.team, self.agent_id = team, agent_id

    def run(self, summary: str, verification: str = "", open_issues: str = "") -> str:
        return self.team.complete(self.agent_id, summary, verification, open_issues)


class Team:
    """对外接口和 Agent 一致（run / cancel / usage / steps / call_log / compactions / messages），
    评测和命令行可以直接替换。"""

    def __init__(self, make_llm, root, permissions: PermissionManager, ui, max_steps: int = 50,
                 context_limit: int = 200_000, read_guard: bool = True, sub_max_steps: int = SUB_MAX_STEPS,
                 delegate: str = "auto", quality_roles: bool = True, processes: ProcessManager | None = None,
                 sandbox=None):
        self.make_llm, self.root, self.permissions, self.ui = make_llm, root, permissions, ui
        self.checkpoints = Checkpoints(root)  # 一轮任务里所有 agent 的修改算一个检查点，一起撤销
        self.sandbox = sandbox  # 沙箱模式：所有 agent 的命令都在同一个容器里执行
        self.mcp = None  # MCP 服务器（启动完成后由 attach_mcp 接上，之后派出的子 agent 也能用）
        self.processes = processes or ProcessManager(sandbox)  # 所有 agent 共用：谁启动的后台进程都能查看和停止
        self.context_limit, self.read_guard, self.sub_max_steps = context_limit, read_guard, sub_max_steps
        self.memory = ProjectMemory(root)
        self.board = Blackboard(on_change=self.memory.save_board)
        self.subagents: dict[str, Agent] = {}
        self.ops: list[dict] = []  # 所有 agent 写文件、改文件、运行命令的成功记录，按时间顺序（重放用）
        self._ops_lock = threading.Lock()
        self._perm_lock = threading.Lock()
        self._seen: dict[str, int] = {}
        self._fresh: set[str] = set()  # 已创建、还没开始运行的子 agent
        self._interrupted: set[str] = set()  # 服务重启时正在运行、恢复后还没重新派发的任务
        self._pool: ThreadPoolExecutor | None = None  # 子 agent 在后台线程里运行（派发不阻塞主 agent）
        self._futures: dict[str, object] = {}  # 正在运行的任务 -> Future
        self._reports: list[str] = []          # 完成了、还没交给主 agent 的汇报
        self._run_lock = threading.Lock()
        self._deliveries: dict[str, dict] = {}  # 任务 -> 这次 complete_task 交付的内容和检查结果
        self._abort = False                    # 这一轮出错 / 被停止：排队还没开始的子任务不再运行
        self._cards_lock = threading.Lock()    # 多个子 agent 同时完成时，模块卡片逐个更新
        self._rejects: dict[str, int] = {}
        self.lead = self._make_agent(LEAD, owned=None, max_steps=max_steps, ui=ui)
        self.lead.tools.update({t.name: t for t in (PlanTasks(self), Dispatch(self), IndexDocs(self),
                                                    MemoryView(self))})
        # 主 agent 的上下文被压缩时，把项目记忆总览直接写进摘要，它不需要把整个项目重读一遍
        self.lead.facts_hook = self.memory.overview
        self.lead.finish_hook = self._lead_finish_hook  # 主 agent 想结束时：还有子 agent 在跑就等它们的汇报
        self.lead.add_tools({})  # 更新工具定义和上下文估算
        self.quality_roles = quality_roles  # 团队模式下测试和安全审查总是出场（主 agent 漏了会被提醒）
        self._lead_prompt = LEAD_PROMPT.replace("{when}", WHEN[delegate]).replace("{roles}", role_guide())
        self.lead.messages[0]["content"] += self._lead_prompt

    # ---------- 和 Agent 一致的接口 ----------

    def run(self, user_input: str, images: list[str] | None = None) -> None:
        self.checkpoints.begin(user_input)
        if not self.board.goal:
            self.board.goal = user_input  # 完整交给子 agent，不截断：规格可能就写在要求里
        self._lead_turn(user_input, images)
        missing = self.missing_quality_roles()
        if missing:  # 主 agent 写了代码却没安排测试或安全审查：提醒一次
            names = "、".join(ROLES[r].name for r in missing)
            self.ui.info(f"团队模式要求测试和安全审查都出场，提醒主 agent 补上：{names}")
            self._lead_turn("Team mode requires the quality roles: " + ", ".join(missing) + " never ran on this work. "
                            "Plan the missing task(s) with plan_tasks (security tasks own no files), dispatch them, act "
                            "on their reports, then summarize.")

    def _lead_turn(self, text: str, images: list[str] | None = None) -> None:
        """主 agent 跑一轮。结束时等所有子 agent 停下；出错、被停止（包括命令行 Ctrl+C）时先让它们停下再等。"""
        self._abort = False
        try:
            self.lead.run(text, images)
        except BaseException:
            self._abort = True
            for a in list(self.subagents.values()):
                a.cancel()
            raise
        finally:
            self._settle()

    def missing_quality_roles(self) -> list[str]:
        """写过代码、但还没有派出过的质量岗位。"""
        if not self.quality_roles or self.cancelled:
            return []
        wrote = any(o["name"] in ("write_file", "edit_file") for o in self.ops)
        ran = {t.get("role") for t in self.board.tasks.values() if t["status"] not in ("pending",)}
        return [r.id for r in QUALITY_ROLES if r.id not in ran] if wrote else []

    def set_scratch(self, scratch: bool) -> None:
        self.lead.set_scratch(scratch, self._lead_prompt)

    def attach_mcp(self, mcp) -> None:
        self.mcp = mcp
        self.lead.add_tools(mcp.tools(self.lead.ws))

    def undo(self, force: bool = False) -> dict:
        return self.lead.undo(force)  # 检查点是共享的；撤销的情况告诉主 agent

    def cancel(self) -> None:
        self.lead.cancel()
        for a in list(self.subagents.values()):
            a.cancel()

    def steer(self, text: str) -> None:
        """运行中用户插话：交给主 agent（它在下一步之前收到，需要的话用黑板转告子 agent）。"""
        self.lead.steer(text)

    # ---------- 后台运行的子 agent ----------

    def running(self) -> set[str]:
        with self._run_lock:
            return {tid for tid, f in self._futures.items() if not f.done()}

    def _take_reports(self) -> str:
        with self._run_lock:
            reports, self._reports = self._reports, []
        return "\n\n".join(reports)

    def _lead_news(self) -> str:
        """主 agent 每一步之后看到的新内容：完成的子任务的汇报 + 黑板上的新内容。"""
        parts = []
        reports = self._take_reports()
        if reports:
            parts.append("[子任务完成]\n" + reports)
        news, self._seen[LEAD] = self.board.digest(LEAD, self._seen.get(LEAD, 0))
        if news:
            parts.append("[黑板更新]\n" + news)
        return "\n\n".join(parts)

    def _lead_finish_hook(self) -> str:
        """主 agent 想结束这一轮时：还有子 agent 在跑，就等下一个完成，把汇报交给它继续。"""
        news = self._lead_news()
        if news:
            return news
        while self.running():
            if self.cancelled:
                raise Cancelled()
            steer = self.lead._drain_inbox()
            if steer:  # 等待期间用户插话：马上交给主 agent，不用等子 agent 做完
                return steer
            with self._run_lock:
                pending = [f for f in self._futures.values() if not f.done()]
            wait(pending, timeout=WAIT_SLICE, return_when=FIRST_COMPLETED)
            news = self._lead_news()
            if news:
                return news
        return self._lead_news()

    def _settle(self) -> None:
        """一轮结束（包括主 agent 步数用完、出错、被停止）：等所有子 agent 停下，没交给主 agent 的汇报留到下一轮开头。"""
        with self._run_lock:
            pending = [f for f in self._futures.values() if not f.done()]
        if pending:
            wait(pending)
        reports = self._take_reports()
        if reports:
            self.lead._pending_note = (self.lead._pending_note + "\n" if self.lead._pending_note else "") + (
                "[上一轮结束时这些子任务才交回，你还没看到它们的汇报：]\n" + reports)

    @property
    def cancelled(self) -> bool:
        return self.lead.cancelled

    def interrupt(self) -> None:
        for a in self.agents:
            a.interrupt()

    # ---------- 保存和恢复（网页服务重启后接着做） ----------

    def export_state(self) -> dict:
        """主 agent 之外需要保存的状态：黑板、操作日志、每个子 agent 的对话。主 agent 的对话由调用方另外保存。"""
        with self._ops_lock:
            ops = list(self.ops)
        return {"board": self.board.to_dict(), "ops": ops, "seen": dict(self._seen),
                "subagents": {tid: {"messages": list(a.messages), "usage": dict(a.usage)}
                              for tid, a in list(self.subagents.items())}}

    def restore_state(self, state: dict) -> list[str]:
        """恢复 export_state 保存的状态。返回服务停止时还在进行、被打断的任务。

        子 agent 带着原来的对话恢复，重新派发时接着做；被打断的任务标记为 interrupted，
        主 agent 下一轮会收到说明，自己决定重新派发。
        """
        board = state.get("board") or {}
        with self.board.lock:
            self.board.goal = board.get("goal", "")
            self.board.contracts = dict(board.get("contracts", {}))
            self.board.tasks = {tid: dict(t) for tid, t in board.get("tasks", {}).items()}
            self.board.events = list(board.get("events", []))
        self.ops = list(state.get("ops", []))
        self._seen = dict(state.get("seen", {}))
        for tid, saved in state.get("subagents", {}).items():
            task = self.board.tasks.get(tid)
            if not task:
                continue
            agent = self._make_agent(tid, task["files"], self._steps_for(tid), PrefixUI(self.ui, tid))
            agent.messages[1:] = saved.get("messages", [])[1:]  # 系统提示按当前版本重新生成
            agent.usage = dict(saved.get("usage", agent.usage))
            agent.interrupt()  # 停在工具调用中间的，补上"已中断"的结果
            self.subagents[tid] = agent
        interrupted = []
        for tid, task in self.board.tasks.items():
            if task["status"] == "running":
                task["status"] = "interrupted" if tid in self.subagents else "pending"
                interrupted.append(tid)
        self._interrupted = {tid for tid in interrupted if tid in self.subagents}
        if interrupted:
            self.lead._pending_note = (self.lead._pending_note + "\n" if self.lead._pending_note else "") + (
                "[The service restarted while these sub-agent tasks were running: " + ", ".join(interrupted)
                + ". Their sub-agents kept their conversation; files they wrote are on disk. Check the board, then "
                "re-dispatch the interrupted tasks so they can continue.]")
        self.board.changed()
        return interrupted

    def reset(self) -> None:
        """清空对话：主 agent 的历史、黑板和所有子 agent。"""
        self.lead.reset()
        self.lead.messages[0]["content"] += self._lead_prompt
        self.board = Blackboard(on_change=self.memory.save_board)
        self.subagents, self._seen, self._fresh = {}, {}, set()
        for name in ("board_read", "board_post", "board_contract"):
            self.lead.tools[name].board = self.board

    def context_tokens(self) -> int:
        return self.lead.context_tokens()

    def compact(self) -> bool:
        return self.lead.compact()

    @property
    def agents(self) -> list[Agent]:
        return [self.lead, *self.subagents.values()]

    @property
    def llm(self):
        return self.lead.llm

    @property
    def messages(self) -> list[dict]:
        return self.lead.messages

    @property
    def usage(self) -> dict:
        return {k: sum(a.usage[k] for a in self.agents) for k in ("prompt", "completion", "cached")}

    @property
    def steps(self) -> int:
        return sum(a.steps for a in self.agents)

    @property
    def compactions(self) -> int:
        return sum(a.compactions for a in self.agents)

    @property
    def call_log(self) -> list[dict]:
        return [{**c, "agent": name} for name, a in [(LEAD, self.lead), *self.subagents.items()] for c in a.call_log]

    @property
    def retries(self) -> int:
        return sum(getattr(a.llm, "retries", 0) for a in self.agents)

    # ---------- 内部 ----------

    def _steps_for(self, tid: str) -> int:
        """子 agent 的步数上限：岗位有自己的上限（安全审查、测试比实现任务少）就取较小的。"""
        role = ROLES.get(self.board.tasks.get(tid, {}).get("role") or "")
        return min(self.sub_max_steps, role.max_steps) if role and role.max_steps else self.sub_max_steps

    def _make_agent(self, agent_id: str, owned: list[str] | None, max_steps: int, ui) -> Agent:
        ws = Workspace(self.root, read_guard=self.read_guard)  # 每个 agent 各自记录读过哪些文件
        tools = build_tools(ws, self.processes, self.sandbox, self.mcp)
        for name in ("write_file", "edit_file", "run_command"):
            tools[name] = Guarded(tools[name], self, agent_id, owned)
        tools["board_read"] = BoardRead(ws, self.board)
        tools["board_post"] = BoardPost(ws, self.board, agent_id)
        tools["board_contract"] = BoardContract(ws, self.board, agent_id)
        tools["spec_section"] = SpecSection(ws, self.memory)
        if agent_id != LEAD:
            tools["complete_task"] = CompleteTask(ws, self, agent_id)
        perms = SharedPermissions(self.permissions, self._locked_ask)
        agent = Agent(self.make_llm(), tools, ws, perms, ui, max_steps=max_steps, context_limit=self.context_limit,
                      sandbox=self.sandbox)
        if agent_id == LEAD:
            agent.step_hook = self._lead_news
        else:
            agent.step_hook = lambda: self._board_news(agent_id)
            agent.finish_tool = "complete_task"  # 子 agent 必须用 complete_task 交付，纯文字回复不算
        agent.checkpoints, agent.checkpoint_turns = self.checkpoints, False
        return agent

    def _locked_ask(self, tool_name: str, preview: str, **kw):
        with self._perm_lock:  # 多个子 agent 同时请求确认时，逐个询问
            return self.permissions.ask(tool_name, preview, **kw)

    def _board_news(self, agent_id: str) -> str:
        text, version = self.board.digest(agent_id, self._seen.get(agent_id, 0))
        self._seen[agent_id] = version
        return f"\n\n[黑板更新]\n{text}" if text else ""

    def owner_of(self, rel: str) -> str | None:
        for tid, t in self.board.tasks.items():
            if _match(rel, t["files"]):
                return tid
        return None

    def log_op(self, agent_id: str, name: str, args: dict, result: str) -> None:
        with self._ops_lock:
            self.ops.append({"agent": agent_id, "name": name, "args": args, "result": result[:200]})

    def plan(self, tasks: list[dict], contracts: list[dict]) -> str:
        ids = [t.get("id", "") for t in tasks]
        if not tasks or any(not i for i in ids) or len(set(ids)) != len(ids) or LEAD in ids:
            raise ToolError("每个任务都需要唯一的 id（不能叫 lead）")
        known = set(ids) | set(self.board.tasks)
        for t in tasks:
            role = ROLES.get(t.get("role", ""))
            if not role:
                raise ToolError(f"任务 {t['id']} 的 role 必须是：{', '.join(ROLES)}")
            if role.read_only:
                t["files"] = []  # 只读岗位（安全审查）不负责任何文件
            elif not t.get("files"):
                raise ToolError(f"任务 {t['id']} 没有指定负责的文件")
            missing = [d for d in t.get("depends", []) if d not in known]
            if missing:
                raise ToolError(f"任务 {t['id']} 依赖了不存在的任务：{missing}")
        for r in QUALITY_ROLES:
            count = sum(1 for t in tasks if t["role"] == r.id) + sum(
                1 for i, t in self.board.tasks.items() if t.get("role") == r.id and i not in ids)
            if count > MAX_PER_QUALITY_ROLE:
                raise ToolError(f"{r.name}（{r.id}）最多 {MAX_PER_QUALITY_ROLE} 个，现在有 {count} 个")
        owned = [(t["id"], f) for t in tasks for f in t["files"]]
        owned += [(i, f) for i, t in self.board.tasks.items() if i not in ids for f in t["files"]]
        for a, fa in owned:
            for b, fb in owned:
                if a < b and (fa == fb or _match(fa, [fb]) or _match(fb, [fa])):
                    raise ToolError(f"文件归属重叠：{a} 的 {fa} 和 {b} 的 {fb}。每个文件只能由一个任务负责")
        for c in contracts:
            self.board.set_contract(LEAD, c["name"], c["text"])
        with self.board.lock:
            for t in tasks:
                old = self.board.tasks.get(t["id"], {})
                self.board.tasks[t["id"]] = {"description": t.get("description", ""), "files": t["files"],
                                             "depends": t.get("depends", []), "context": t.get("context", []),
                                             "spec_sections": t.get("spec_sections", []), "role": t["role"],
                                             "status": old.get("status", "pending"), "report": old.get("report", "")}
            self.board.changed()
        missing = [x for t in tasks for x in self.memory.sections(t.get("spec_sections", []))[1]]
        note = f"\n注意：这些需求小节编号不存在：{missing}（先用 index_docs 建索引）" if missing else ""
        return "计划已写入黑板：\n" + self.board.snapshot() + note

    def dispatch(self, task_ids: list[str], feedback: str = "") -> str:
        """派出子 agent，马上返回：它们在后台并行运行，每个完成后汇报在主 agent 的下一步送到。"""
        busy = self.running()
        for tid in task_ids:
            t = self.board.tasks.get(tid)
            if not t:
                raise ToolError(f"没有任务 {tid}，请先用 plan_tasks 登记")
            if tid in busy:
                raise ToolError(f"任务 {tid} 正在运行，等它交回后再派发")
            waiting = [d for d in t["depends"] if self.board.tasks.get(d, {}).get("status") != "done"]
            if waiting:
                raise ToolError(f"任务 {tid} 依赖的任务还没完成：{waiting}")
        self.refresh_cards()  # 主 agent 自己写的公共代码也要有卡片，子 agent 才能拿到它的接口
        self.ui.info(f"派出子 agent：{', '.join(task_ids)}")
        if self._pool is None:
            self._pool = ThreadPoolExecutor(max_workers=MAX_PARALLEL, thread_name_prefix="sub")
        for tid in task_ids:  # 先在主线程里按顺序创建，再放到后台运行
            if tid not in self.subagents:
                self.subagents[tid] = self._make_agent(tid, self.board.tasks[tid]["files"], self._steps_for(tid),
                                                       PrefixUI(self.ui, tid))
                self._fresh.add(tid)
            self.board.set_status(tid, "running")
            with self._run_lock:
                self._futures[tid] = self._pool.submit(self._run_in_background, tid, feedback)
        return (f"已派出：{', '.join(task_ids)}，在后台并行运行。每个任务完成后，汇报会自动送到你这里；"
                "你可以先做别的事（不要改它们负责的文件），没事可做时直接结束这一步，系统会等它们完成。")

    def _run_in_background(self, tid: str, feedback: str) -> None:
        if self._abort or self.cancelled:  # 排队期间这一轮已经停止了：不再开始（开始运行时会清掉停止标志）
            self.board.set_status(tid, "cancelled")
            with self._run_lock:
                self._reports.append(f"## {tid}：已停止（还没开始）")
            return
        try:
            report = self._run_sub(tid, feedback)
        except Cancelled:
            report = f"## {tid}：已停止"
        except BaseException as e:  # 不让后台线程静默崩溃：交给主 agent 决定
            self.board.set_status(tid, "failed", f"{type(e).__name__}: {e}")
            report = f"## {tid}：失败\n{type(e).__name__}: {e}"
        self.refresh_cards()
        with self._run_lock:
            self._reports.append(report)

    # ---------- 交付 ----------

    def complete(self, tid: str, summary: str, verification: str, open_issues: str) -> str:
        """子 agent 的 complete_task：机械检查交付，不通过退回给它自己改（参考 OPC 的交付检查）。"""
        agent = self.subagents[tid]
        problems = self.delivery_problems(tid, summary, verification)
        self._rejects[tid] = self._rejects.get(tid, 0) + (1 if problems else 0)
        if problems and self._rejects[tid] < MAX_COMPLETE_REJECTS:
            left = MAX_COMPLETE_REJECTS - self._rejects[tid]
            return ("错误：交付检查没通过，请改好后重新调用 complete_task：\n" + "\n".join(f"- {x}" for x in problems)
                    + f"\n（还可以提交 {left} 次，之后会带着这些问题交给主 agent）")
        self._deliveries[tid] = {"summary": summary, "verification": verification, "open_issues": open_issues,
                                 "problems": problems}
        agent.mark_finished()
        return "已交付" + ("（交付检查仍有问题，已在汇报里注明）" if problems else "，交付检查通过")

    def delivery_problems(self, tid: str, summary: str, verification: str) -> list[str]:
        t, agent = self.board.tasks[tid], self.subagents[tid]
        root, problems = Path(self.root), []
        if not summary.strip():
            problems.append("summary 不能为空：写明做了什么、改了哪些文件")
        role = ROLES.get(t.get("role") or "")
        if not (role and role.read_only):
            for pattern in t["files"]:
                if any(ch in pattern for ch in "*?["):
                    if not any(p.is_file() for p in root.glob(pattern)):
                        problems.append(f"你负责的 {pattern} 一个文件都没有")
                elif not (root / pattern).is_file():
                    problems.append(f"你负责的文件 {pattern} 不存在")
        with self._ops_lock:
            written = {o["args"].get("path") for o in self.ops if o["agent"] == tid and o["args"].get("path")}
        for rel in sorted(p for p in written if p and p.endswith(".py")):
            f = root / rel
            if f.is_file():
                try:
                    compile(f.read_text(encoding="utf-8", errors="replace"), rel, "exec")
                except SyntaxError as e:
                    problems.append(f"{rel} 有语法错误（第 {e.lineno} 行：{e.msg}）")
        if agent._dirty and not verification.strip():
            problems.append(f"改过代码（{'、'.join(agent._dirty[:5])}）之后没有成功运行过验证：运行测试或脚本验证；"
                            "确实没法验证的，在 verification 里说明原因")
        return problems

    def refresh_cards(self) -> None:
        """为所有写过的文件更新模块卡片（接口从代码里提取），删除已经不存在的文件的卡片。"""
        with self._cards_lock:  # 多个子 agent 同时完成时会同时调用
            self._refresh_cards()

    def _refresh_cards(self) -> None:
        ws = self.lead.ws
        with self._ops_lock:
            paths = {o["args"].get("path") for o in self.ops if o["args"].get("path")}
        for raw in paths:
            try:
                rel = ws.rel(ws.resolve(raw))
            except WorkspaceError:
                continue
            owner = self.owner_of(rel)
            spec = self.board.tasks.get(owner, {}).get("spec_sections", []) if owner else []
            self.memory.update_card(rel, task=owner or LEAD, spec=spec)

    def _spec_text(self, task: dict) -> str:
        text, missing = self.memory.sections(task.get("spec_sections", []))
        if missing:
            text += f"{NL}{NL}(Unknown section ids: {', '.join(missing)})"
        return text or "(none: read the spec yourself if you need it)"

    def _dependency_cards(self, tid: str) -> str:
        """依赖的任务负责的文件，以及主 agent 写的公共代码：只给接口卡片，不给实现。"""
        deps = self.board.tasks[tid]["depends"]
        paths = [p for p, c in self.memory.cards.items() if c.get("task") in deps or c.get("task") == LEAD]
        return self.memory.cards_for(sorted(paths)) or "(none)"

    def _preload(self, agent: Agent, paths: list[str]) -> str:
        """把主 agent 指定的文件内容直接放进子 agent 的任务说明，并记为"已读"（之后可以直接修改）。

        按任务分配上下文：子任务需要的规格、依赖的模块、要改的代码一开始就交给它，而不是让它自己从头摸索。
        """
        parts, used, skipped = [], 0, []
        for path in dict.fromkeys(paths):  # 去重，保持顺序
            try:
                p = agent.ws.resolve(path)
            except WorkspaceError:
                skipped.append(f"{path}（不在工作区内）")
                continue
            if not p.is_file():
                skipped.append(f"{path}（开始时还不存在）")
                continue
            if p.stat().st_size > MAX_FILE_BYTES or is_binary(p):
                skipped.append(f"{path}（二进制或过大）")
                continue
            text = read_text(p)[0]
            if agent.redact:  # 和工具结果一样遮蔽密钥
                text = redact(text)[0]
            if used + len(text) > PRELOAD_CHARS:
                skipped.append(f"{path}（内容太多，请自己用 read_file 读取）")
                continue
            used += len(text)
            agent.ws.mark_seen(p)
            parts.append(f"## {agent.ws.rel(p)}" + NL + "```" + NL + text + NL + "```")
        if skipped:
            parts.append("Not preloaded: " + "; ".join(skipped))
        return (NL + NL).join(parts) or "(none)"

    def _run_sub(self, tid: str, feedback: str) -> str:
        t = self.board.tasks[tid]
        agent = self.subagents[tid]
        if tid in self._fresh:  # 第一次派出；返工时沿用之前的上下文，它记得自己做过什么
            self._fresh.discard(tid)
            # 契约和已有的决策、留言直接写在任务说明里，黑板只推送之后的新内容（先记版本号，宁可重复不要遗漏）
            self._seen[tid] = len(self.board.events)
            contracts = "\n".join(f"- {n}: {c['text']}" for n, c in self.board.contracts.items()) or "(none)"
            role = ROLES[t.get("role") or "backend"]
            prompt = SUB_PROMPT.format(goal=self.board.goal, task_id=tid, description=t["description"],
                                       role_name=f"{role.id}（{role.name}）", role_duty=role.duty,
                                       files="\n".join(f"- {f}" for f in t["files"]), contracts=contracts,
                                       notes=self.board.notes_for(tid),
                                       spec=self._spec_text(t), cards=self._dependency_cards(tid),
                                       preloaded=self._preload(agent, t.get("context", [])))
        elif tid in self._interrupted:
            self._interrupted.discard(tid)
            prompt = ("The service restarted while you were working on this task. Continue where you left off: "
                      "files you already wrote are on disk (re-read them before editing).")
        else:
            prompt = "The lead sent your task back for rework."
        if feedback:
            prompt += f"\n\n# Feedback from the lead\n{feedback}"
        rework = t.get("report") is not None and t.get("status") == "running" and bool(t.get("report"))
        with self._ops_lock:
            ops_before = len(self.ops)
        self._deliveries.pop(tid, None)
        self._rejects[tid] = 0
        try:
            agent.run(prompt)
        except Cancelled:
            self.board.set_status(tid, "cancelled")
            raise
        except Exception as e:  # 子 agent 出错（比如 API 失败）：交回给主 agent 决定怎么办
            self.board.set_status(tid, "failed", f"{type(e).__name__}: {e}")
            return f"## {tid}：失败\n{type(e).__name__}: {e}"
        delivery = self._deliveries.get(tid)
        if delivery:  # 用 complete_task 交付了：汇报就是交付的内容和检查结果
            report = delivery["summary"]
            if delivery["verification"]:
                report += f"\n验证：{delivery['verification']}"
            if delivery["open_issues"]:
                report += f"\n未解决：{delivery['open_issues']}"
            if delivery["problems"]:
                report += "\n交付检查没通过：" + "；".join(delivery["problems"])
        else:  # 没有交付（步数用完、一直不调用 complete_task）：拿最后一条回复
            report = next((m["content"] for m in reversed(agent.messages)
                           if m["role"] == "assistant" and m.get("content")), "")
        finished = bool(delivery)
        report = report if len(report) <= REPORT_CHARS else report[:REPORT_CHARS] + "…"
        self.board.set_status(tid, "done" if finished else "unfinished", report)
        with self._ops_lock:
            changed = sorted({o["args"].get("path") for o in self.ops if o["agent"] == tid and o["args"].get("path")})
            changed_now = sorted({o["args"].get("path") for o in self.ops[ops_before:]
                                  if o["agent"] == tid and o["args"].get("path") and o["name"] != "run_command"})
        if rework and changed_now:
            self._notify_dependents(tid, changed_now)
        state = "完成" if finished else "未完成（没有用 complete_task 交付，可能是步数用完了）"
        return f"## {tid}：{state}\n改动的文件：{', '.join(changed) or '无'}\n汇报：{report or '（没有汇报）'}"

    def _notify_dependents(self, tid: str, files: list[str]) -> None:
        """返工改了文件：依赖它、已经完成的任务可能要同步。通知主 agent（由它决定要不要重新派发）和这些任务。"""
        users = [i for i, t in self.board.tasks.items() if tid in t["depends"] and t["status"] == "done"]
        if not users:
            return
        text = f"{tid} 返工改了 {', '.join(files)}；依赖它、已经完成的任务：{', '.join(users)}，可能需要同步"
        self.board.post(tid, "note", text + "（需要的话重新派发它们，并说明改了什么）", to=LEAD)
        for u in users:
            self.board.post(tid, "note", f"你依赖的 {tid} 返工改了 {', '.join(files)}，再次派给你时请对照检查", to=u)


class PlanTasks(Tool):
    name = "plan_tasks"
    description = ("登记子任务和接口契约（写入共享黑板）。每个任务负责一组互不重叠的文件（路径或通配符），"
                   "可以声明依赖。再次调用可以新增任务或修改未完成的任务。")
    parameters = {
        "type": "object",
        "properties": {
            "tasks": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "简短的英文 id，例如 storage"},
                    "role": {"type": "string", "enum": list(ROLES),
                             "description": "岗位：开发岗位按项目选；tester 和 security 在团队模式下总是要有"},
                    "description": {"type": "string", "description": "完整的任务说明：要实现什么、对应需求的哪些条目、怎么自测"},
                    "files": {"type": "array", "items": {"type": "string"}, "description": "负责的文件，例如 pkg/store.py、pkg/models/*.py"},
                    "depends": {"type": "array", "items": {"type": "string"}},
                    "spec_sections": {"type": "array", "items": {"type": "string"},
                                      "description": "这个任务实现的需求小节编号（index_docs 给出的 S1、S2……），原文会交给子 agent"},
                    "context": {"type": "array", "items": {"type": "string"},
                                "description": "子 agent 需要阅读的文件（规格、依赖的模块、要修改的已有代码），一开始就把内容交给它"},
                },
                "required": ["id", "role", "description", "files"]}},
            "contracts": {"type": "array", "items": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "text": {"type": "string", "description": "精确的接口：函数签名、参数和返回值、数据格式、错误处理"}},
                "required": ["name", "text"]}},
        },
        "required": ["tasks"],
    }

    def __init__(self, team: Team):
        super().__init__(team.lead.ws)
        self.team = team

    def run(self, tasks: list, contracts: list | None = None) -> str:
        return self.team.plan(tasks, contracts or [])


class Dispatch(Tool):
    name = "dispatch"
    description = ("把已登记的任务派给子 agent，在后台并行运行，马上返回。每个任务完成后汇报会自动送到你这里，"
                   "可以随时派出依赖已经满足的任务。返工时再次派出同一个任务并附上具体意见，子 agent 会保留之前的上下文。")
    parameters = {
        "type": "object",
        "properties": {
            "task_ids": {"type": "array", "items": {"type": "string"}},
            "feedback": {"type": "string", "description": "返工意见：失败的测试、期望和实际结果"},
        },
        "required": ["task_ids"],
    }

    def __init__(self, team: Team):
        super().__init__(team.lead.ws)
        self.team = team

    def run(self, task_ids: list, feedback: str = "") -> str:
        return self.team.dispatch(task_ids, feedback)


class IndexDocs(Tool):
    name = "index_docs"
    description = "把需求文档按标题切成带编号的小节（S1、S2……）存进项目记忆，返回目录。拆任务时用编号指定每个任务实现哪些小节。"
    parameters = {"type": "object", "properties": {"paths": {"type": "array", "items": {"type": "string"}}},
                  "required": ["paths"]}

    def __init__(self, team: "Team"):
        super().__init__(team.lead.ws)
        self.team = team

    def run(self, paths: list) -> str:
        for path in paths:
            p = self.ws.resolve(path)
            if not p.is_file():
                raise ToolError(f"{path} 不是文件")
            self.team.memory.index_doc(self.ws.rel(p))
        return self.team.memory.outline()


class SpecSection(Tool):
    name = "spec_section"
    description = "读取需求文档里指定编号小节的原文（编号见项目记忆里的需求目录，例如 S3）。"
    parameters = {"type": "object", "properties": {"ids": {"type": "array", "items": {"type": "string"}}},
                  "required": ["ids"]}

    def __init__(self, workspace, memory: ProjectMemory):
        super().__init__(workspace)
        self.memory = memory

    def run(self, ids: list) -> str:
        text, missing = self.memory.sections(ids)
        if missing and not text:
            raise ToolError(f"没有这些小节：{missing}。需求目录：{NL}{self.memory.outline() or '（还没有建索引）'}")
        return text + (f"{NL}{NL}（没有这些小节：{missing}）" if missing else "")


class MemoryView(Tool):
    name = "memory"
    description = "查看项目记忆总览：需求目录、接口契约、任务看板、每个代码文件的卡片（接口和依赖）。需要全局信息时用它，不要把整个项目重读一遍。"

    def __init__(self, team: "Team"):
        super().__init__(team.lead.ws)
        self.team = team

    def run(self) -> str:
        self.team.refresh_cards()
        return self.team.memory.overview()


class PrefixUI:
    """子 agent 的界面：给工具调用和提示加上任务名；并行时逐字输出会交错，所以不转发。"""

    def __init__(self, ui, prefix: str):
        self.ui, self.prefix = ui, prefix

    def tool_call(self, name, args):
        tagged = getattr(self.ui, "sub_tool_call", None)
        if tagged:
            return tagged(self.prefix, name, args)
        return self.ui.tool_call(name, args)

    def tool_result(self, result):
        tagged = getattr(self.ui, "sub_tool_result", None)
        return tagged(self.prefix, result) if tagged else self.ui.tool_result(result)

    def info(self, text):
        return self.ui.info(f"[{self.prefix}] {text}")

    def warn(self, text):
        return self.ui.warn(f"[{self.prefix}] {text}")

    def assistant(self, text, reasoning=None):
        if text:
            self.ui.info(f"[{self.prefix}] {text[:300]}")

    def __getattr__(self, name):  # delta 等：不转发
        return lambda *a, **k: None


def team_messages(team: Team) -> dict:
    """评测轨迹里保存的团队信息。"""
    return {"board": team.board.to_dict(), "ops": team.ops,
            "subagents": {tid: a.messages for tid, a in team.subagents.items()}}


__all__ = ["Team", "Blackboard", "team_messages", "LEAD"]
