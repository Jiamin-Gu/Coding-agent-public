"""Web 会话管理。

- Conversation：一次对话 = 一个工作区 + 一个 agent + 事件日志，可保存到本地
- Hub：管理当前对话和所有浏览器连接，处理浏览器发来的消息
"""
import asyncio
import itertools
import threading
import time
import shutil
from pathlib import Path

from openai import APIError

from .. import __version__
from ..agent import Agent, Cancelled
from ..checkpoints import describe
from ..permissions import PermissionManager, rules_file
from ..mcp import MCPManager
from ..sandbox import DockerSandbox
from ..shadow import Shadow, describe as describe_changes
from ..store import Store, new_id, now
from ..team import Team
from ..tools import ProcessManager, build_tools
from ..workspace import Workspace

# 这些工具执行后，文件树需要刷新
FILE_TOOLS = {"write_file", "edit_file", "run_command"}
TITLE_LEN = 30
MAX_IMAGES = 4
SAVE_EVERY = 3  # 任务进行中每隔几秒保存一次对话（秒）
MCP_START_WAIT = 90  # 发消息时最多等 MCP 服务器启动多久（秒）
IMAGE_ONLY_PROMPT = "请看图片。"  # 只发图片不写字时，给模型的默认文字


class WebUI:
    """实现和 ConsoleUI 相同的接口，只是输出变成事件。"""

    def __init__(self, conv: "Conversation"):
        self.c = conv
        self._ids = itertools.count(1)
        self._current: dict | None = None  # 正在执行的工具调用
        self._pending: dict[int, dict] = {}  # 等待用户回应的权限请求
        self._sub_current: dict[str, dict] = {}  # 团队模式：每个子 agent 正在执行的工具调用

    def sync_ids(self, events: list[dict]) -> None:
        """从历史事件恢复对话时，新的 id 要接着往后编，避免和旧卡片冲突。"""
        top = max((e.get("id", 0) for e in events if isinstance(e.get("id"), int)), default=0)
        self._ids = itertools.count(top + 1)

    def delta(self, kind: str, text: str) -> None:
        # 流式片段不进日志：最终的完整消息会再发一次 assistant 事件
        self.c.emit({"type": "delta", "kind": kind, "text": text}, log=False)

    def assistant(self, text: str, reasoning: str | None = None) -> None:
        self.c.emit({"type": "assistant", "text": text, "reasoning": reasoning})
        self.c.hub.push_state()  # 每次模型调用后更新 token 用量

    def tool_call(self, name: str, args: dict) -> None:
        self._current = {"id": next(self._ids), "name": name, "args": args}
        self.c.emit({"type": "tool_call", **self._current})

    def tool_result(self, result: str) -> None:
        call = self._current or {"id": next(self._ids), "name": "", "args": {}}
        is_error = result.startswith(("错误", "用户拒绝"))
        self.c.emit({"type": "tool_result", "id": call["id"], "result": result, "is_error": is_error})
        if not is_error and call["name"] in ("write_file", "edit_file"):
            self.c.changed_files.add(call["args"].get("path", ""))
        if call["name"] in FILE_TOOLS:
            self.c.emit({"type": "files_changed", "changed": sorted(self.c.changed_files)}, log=False)
        self._current = None

    def sub_tool_call(self, who: str, name: str, args: dict) -> None:
        """团队模式：子 agent 的工具调用，卡片上标出是哪个子 agent。多个子 agent 并行，各自记录当前调用。"""
        call = {"id": next(self._ids), "name": name, "args": args, "agent": who}
        self._sub_current[who] = call
        self.c.emit({"type": "tool_call", **call})

    def sub_tool_result(self, who: str, result: str) -> None:
        saved, self._current = self._current, self._sub_current.pop(who, None)
        self.tool_result(result)
        self._current = saved

    def info(self, text: str) -> None:
        self.c.emit({"type": "notice", "level": "info", "text": text})

    def warn(self, text: str) -> None:
        self.c.emit({"type": "notice", "level": "warn", "text": text})

    def error(self, text: str) -> None:
        self.c.emit({"type": "notice", "level": "error", "text": text})

    def ask_permission(self, tool_name: str, preview: str, prefix: str | None = None,
                       network: bool = False) -> tuple[str, str]:
        """在 agent 线程里调用：发出请求，然后阻塞等待浏览器回应。"""
        req = {"id": next(self._ids), "event": threading.Event(), "answer": ("n", "")}
        self._pending[req["id"]] = req
        call_id = self._current["id"] if self._current else None
        self.c.emit({"type": "permission_request", "id": req["id"], "call_id": call_id,
                     "tool": tool_name, "preview": preview, "prefix": prefix, "network": network})
        while not req["event"].wait(0.2):
            if self.c.agent.cancelled:
                req["answer"] = ("n", "")
                break
        del self._pending[req["id"]]
        self.c.emit({"type": "permission_resolved", "id": req["id"], "choice": req["answer"][0]})
        return req["answer"]

    def answer_permission(self, req_id: int, choice: str, feedback: str) -> None:
        req = self._pending.get(req_id)
        if req and choice in ("y", "n", "a", "p"):
            req["answer"] = (choice, feedback)
            req["event"].set()


class Conversation:
    def __init__(self, hub: "Hub", workspace: str | Path, data: dict | None = None):
        self.hub = hub
        data = data or {}
        self._save_lock = threading.Lock()  # 子 agent 并行时，多个线程可能同时触发保存
        self._last_save = time.time()
        self.id = data.get("id") or new_id()
        self.title = data.get("title") or "新对话"
        self.created = data.get("created") or now()
        self.updated = data.get("updated") or self.created
        self.real_root = Path(workspace).resolve()  # 用户的真实项目
        self.scratch = bool(data.get("scratch"))  # 临时工作区：用户没有选项目，直接来问问题
        # 沙箱模式下 agent 在工作区的副本上干活（见 shadow.py），真实项目等用户确认后才改；临时工作区本来就是隔离的，不用副本
        self.shadow: Shadow | None = self._new_shadow() if hub.sandbox and not self.scratch else None
        self.workspace = Workspace(self.shadow.copy if self.shadow else self.real_root)
        self.ui = WebUI(self)
        self.sandbox = self._new_sandbox() if hub.sandbox else None  # 第一次执行命令时才启动容器
        self.processes = ProcessManager(self.sandbox)  # 这个对话里 agent 启动的后台进程，离开对话时终止
        # MCP 服务器在后台启动（npx 第一次运行可能要几十秒），发消息前等它就绪再把工具接上
        self.mcp = MCPManager(self.workspace.root, config={} if hub.demo else None)
        self._mcp_ready = threading.Event()
        self._mcp_attached = False
        threading.Thread(target=self._start_mcp, daemon=True).start()
        self.permissions = PermissionManager(ask=self.ui.ask_permission, auto=hub.auto,
                                             rules_path=rules_file(self.real_root))
        self.team = bool(data.get("team", hub.team))
        self.agent = self._build_agent()
        self.events: list[dict] = data.get("events", [])
        self.changed_files: set[str] = set(data.get("changed", []))
        if data.get("messages"):
            # system prompt 每次重新生成（日期、AGENT.md 可能变了），其余历史原样恢复
            messages = hub.store.unpack_messages(data["messages"])
            self.agent.messages[1:] = messages[1:]  # 团队模式：恢复的是主 agent 的历史（子 agent 和黑板不保存）
            usage = data.get("usage", self.agent.usage)
            (self.agent.lead if self.team else self.agent).usage = dict(usage)
        if self.team and data.get("team_state"):
            self._restore_team(data["team_state"], data.get("usage", {}))
        self.ui.sync_ids(self.events)
        self.busy = False

    def _restore_team(self, state: dict, total: dict) -> None:
        for sub in state.get("subagents", {}).values():
            sub["messages"] = self.hub.store.unpack_messages(sub.get("messages", []))
        interrupted = self.agent.restore_state(state)
        self.agent.lead.interrupt()  # 主 agent 停在派发中间的，补上"已中断"的结果
        # 保存的用量是全队合计，扣掉子 agent 的部分才是主 agent 自己的
        for k in ("prompt", "completion", "cached"):
            subs = sum(a.usage.get(k, 0) for a in self.agent.subagents.values())
            self.agent.lead.usage[k] = max(0, total.get(k, 0) - subs)
        if interrupted:
            self.events.append({"type": "notice", "level": "warn",
                                "text": f"服务重启前这些子任务还在进行：{'、'.join(interrupted)}。团队状态已恢复，"
                                        "输入“继续”让主 agent 重新派发，子 agent 会接着之前的进度做"})

    def _build_agent(self):
        """团队模式下是主 agent + 子 agent（对外接口一致）；否则是单个 agent。"""
        h = self.hub
        if self.team:
            agent = Team(lambda: h.llm, self.workspace.root, self.permissions, self.ui, max_steps=h.max_steps,
                         context_limit=h.context_limit, processes=self.processes, sandbox=self.sandbox)
        else:
            agent = Agent(h.llm, build_tools(self.workspace, self.processes, self.sandbox), self.workspace,
                          self.permissions, self.ui, max_steps=h.max_steps, max_tool_output=h.max_tool_output,
                          context_limit=h.context_limit, sandbox=self.sandbox)
        if getattr(self, "scratch", False):
            agent.set_scratch(True)
        return agent

    def set_sandbox(self, enabled: bool) -> str | None:
        """切换沙箱模式：停掉之前的后台进程和容器，换到副本（或回到真实项目），按新模式重建 agent（保留对话历史）。
        副本里还有没应用的改动时不能关：先应用或放弃。返回错误信息。"""
        if enabled == bool(self.sandbox):
            return None
        if not enabled and self.shadow and self.shadow.pending():
            return "沙箱副本里还有没应用到项目的改动：先点「应用到项目」或「放弃」，再关闭沙箱"
        self.close()
        if enabled and not self.scratch:
            self.shadow = self._new_shadow()
        elif not enabled and self.shadow:
            self.shadow.remove()
            self.shadow = None
        self.workspace = Workspace(self.shadow.copy if self.shadow else self.real_root)
        self.sandbox = self._new_sandbox() if enabled else None
        self.processes = ProcessManager(self.sandbox)
        self.rebuild_agent()
        return None

    def _new_shadow(self) -> Shadow:
        shadow = Shadow(self.real_root, self.hub.store.home / "sandbox-copies" / self.id)
        shadow.ensure()
        return shadow

    def shadow_changes(self) -> dict | None:
        """副本里待应用的改动；没有副本或没有改动时返回 None。"""
        if not self.shadow:
            return None
        ch = self.shadow.changes()
        return ch if any(ch.values()) else None

    def _start_mcp(self) -> None:
        try:
            self.mcp.start()
        finally:
            self._mcp_ready.set()

    def attach_mcp(self) -> None:
        """把启动完成的 MCP 服务器的工具接到 agent 上（切换模式重建 agent 后要重新接）。"""
        if self._mcp_attached or not self.mcp.config:
            return
        self._mcp_ready.wait(MCP_START_WAIT)
        if self.team:
            self.agent.attach_mcp(self.mcp)
        else:
            self.agent.add_tools(self.mcp.tools(self.workspace))
        self._mcp_attached = True
        for name, err in self.mcp.errors.items():
            self.ui.warn(f"MCP 服务器 {name} 启动失败：{err}")

    def _new_sandbox(self) -> DockerSandbox:
        sandbox = DockerSandbox(self.workspace.root)
        # 开发服务器的预览地址变化时推给界面（顶栏显示可以点开的链接）
        sandbox.forwarder.on_change = lambda items: (self.hub.push_state() if self.hub.current is self else None)
        return sandbox

    def close(self) -> None:
        """离开这个对话：终止后台进程，删除沙箱容器，关闭 MCP 服务器。"""
        self.processes.stop_all()
        self.mcp.close()
        if self.sandbox:
            self.sandbox.stop()

    def set_team(self, value: bool) -> None:
        """切换模式：保留对话历史（系统提示按新模式重新生成）。"""
        if value != self.team:
            self.team = value
            self.rebuild_agent()

    def rebuild_agent(self) -> None:
        """切换模式或模型后重新创建 agent，保留对话历史和用量。"""
        old = self.agent
        self.agent = self._build_agent()
        self._mcp_attached = False  # 新的 agent 下次运行前重新接上 MCP 工具
        self.agent.messages[1:] = old.messages[1:]
        (self.agent.lead if self.team else self.agent).usage = dict(old.usage)

    def emit(self, event: dict, log: bool = True) -> None:
        if log:
            self.events.append(event)
        self.hub.broadcast(self, event)
        # 任务进行中也定期保存：服务被关掉（关窗口、重启电脑）时，最多丢掉最近几秒的进度
        if getattr(self, "busy", False) and time.time() - self._last_save > SAVE_EVERY:
            try:
                self.save()
            except Exception:
                pass  # 保存失败不影响任务本身，结束时还会再保存一次

    def to_dict(self) -> dict:
        data = {
            "id": self.id, "title": self.title, "workspace": str(self.real_root),
            "created": self.created, "updated": self.updated,
            "messages": self.hub.store.pack_messages(self.agent.messages), "events": list(self.events),
            "changed": sorted(self.changed_files), "usage": self.agent.usage, "team": self.team,
            "scratch": self.scratch,
        }
        if self.team:  # 团队模式：黑板和每个子 agent 的对话也保存，服务重启后可以接着做
            state = self.agent.export_state()
            for sub in state["subagents"].values():
                sub["messages"] = self.hub.store.pack_messages(sub["messages"])
            data["team_state"] = state
        return data

    def save(self) -> None:
        with self._save_lock:
            self.updated = now()
            self._last_save = time.time()
            self.hub.store.save(self.to_dict())

    def start(self, text: str, image_ids: list[str] | None = None) -> None:
        image_ids = image_ids or []
        self.busy = True
        if self.title == "新对话":
            label = text or "图片"
            self.title = label[:TITLE_LEN] + ("…" if len(label) > TITLE_LEN else "")
        event = {"type": "user", "text": text}
        if image_ids:
            event["images"] = image_ids  # 事件里只存图片 id，界面通过 /api/image/<id> 显示
        self.emit(event)
        self.save()
        self.hub.push_meta()
        images = [self.hub.store.image_data_url(i) for i in image_ids]
        threading.Thread(target=self._run, args=(text or IMAGE_ONLY_PROMPT, images), daemon=True).start()

    def steer(self, text: str) -> None:
        """运行中用户插话：显示出来，交给 agent（团队模式交给主 agent）。"""
        self.emit({"type": "user", "text": text, "interject": True})
        self.agent.steer(text)

    def _run(self, text: str, images: list[str]) -> None:
        try:
            self.attach_mcp()
            if self.shadow:  # 没有待应用的改动时，把用户在项目里的修改同步进副本
                synced = self.shadow.refresh()
                if synced:
                    self.ui.info(f"已把你在项目里改动的 {len(synced)} 个文件同步进沙箱副本")
            self.agent.run(text, images)
        except Cancelled:
            self.agent.interrupt()
            self.ui.warn("已停止")
        except APIError as e:
            self.agent.interrupt()
            hint = ""
            if images and getattr(e, "status_code", None) == 400:
                hint = "（当前模型可能不支持图片输入，可以换一个支持视觉的模型，或新建对话不带图片重试）"
            self.ui.error(f"API 调用失败：{e}{hint}")
        except Exception as e:  # 不让后台线程静默崩溃
            self.agent.interrupt()
            self.ui.error(f"{type(e).__name__}: {e}")
        finally:
            self.busy = False
            ch = self.shadow_changes() if self.shadow else None
            if ch:  # 每轮结束列出副本里的改动，用户决定应用到项目还是放弃
                self.emit({"type": "sandbox_changes", "summary": describe_changes(ch), "changes": ch})
            self.emit({"type": "done"})
            self.save()
            self.hub.push_meta()


class Hub:
    def __init__(self, llm, store: Store | None = None, auto: bool = False,
                 max_steps: int = 50, max_tool_output: int = 12_000, demo: bool = False,
                 context_limit: int = 200_000, sandbox: bool = False):
        self.llm = llm
        self.sandbox = sandbox  # 新对话是否用沙箱模式
        self.demo = demo
        self.store = store or Store()
        self.auto = auto
        self.max_steps = max_steps
        self.max_tool_output = max_tool_output
        self.context_limit = context_limit
        self.team = False  # 新对话是否用团队模式
        self.current: Conversation | None = None
        self._clients: dict[asyncio.Queue, asyncio.AbstractEventLoop] = {}
        self._lock = threading.Lock()

    def set_sandbox(self, enabled: bool) -> str | None:
        """在设置里开关沙箱模式。返回错误信息。"""
        if self.busy:
            return "任务运行中，请先停止再修改设置"
        if self.current:
            err = self.current.set_sandbox(enabled)
            if err:
                return err
        self.sandbox = enabled
        self.push_state()
        return None

    def set_llm(self, llm) -> str | None:
        """在设置里换了模型或服务商：之后的请求都用新的客户端，当前对话保留历史。返回错误信息。"""
        if self.busy:
            return "任务运行中，请先停止再修改设置"
        self.llm = llm
        if self.current:
            self.current.rebuild_agent()
        self.push_state()
        return None

    # ---------- 打开对话 ----------

    def open_workspace(self, path: str) -> str | None:
        """在指定工作区开一个新对话。返回错误信息，成功返回 None。"""
        p = Path(path.strip().strip('"')).expanduser()
        if not p.is_dir():
            return f"目录不存在：{path}"
        self._switch(Conversation(self, p.resolve()))
        self.store.add_recent_workspace(str(self.current.real_root))
        return None

    def open_scratch(self) -> None:
        """不选工作区直接提问：开一个用临时工作区的新对话（不进"最近使用的工作区"）。"""
        path = self.store.home / "scratch" / new_id()
        path.mkdir(parents=True, exist_ok=True)
        self._switch(Conversation(self, path.resolve(), {"scratch": True}))

    def open_latest(self) -> None:
        for item in self.store.list_conversations():
            if self.open_conversation(item["id"]) is None:
                return

    def open_conversation(self, conv_id: str) -> str | None:
        data = self.store.load(conv_id)
        if not data:
            return "对话不存在"
        if not Path(data["workspace"]).is_dir():
            return f"这个对话的工作区已不存在：{data['workspace']}"
        self._switch(Conversation(self, data["workspace"], data))
        return None

    def _remove_shadow(self, conv_id: str) -> None:
        """删除对话时连它的沙箱副本一起删（副本里没应用的改动也就不要了）。"""
        path = self.store.home / "sandbox-copies" / conv_id
        if self.current and self.current.id == conv_id:
            self.current.close()
        Shadow(path, path).remove()

    def _remove_scratch_dir(self, conv_id: str) -> None:
        """删除临时对话时连临时工作区一起删（那是 agent 自己测试用的，不是用户的文件）。"""
        data = self.store.load(conv_id)
        if not data or not data.get("scratch"):
            return
        path, base = Path(data["workspace"]).resolve(), (self.store.home / "scratch").resolve()
        if path.is_relative_to(base) and path != base:
            if self.current and self.current.id == conv_id:
                self.current.close()  # 先停掉它的后台进程，Windows 上占用中的文件删不掉
            shutil.rmtree(path, ignore_errors=True)

    def _switch(self, conv: "Conversation | None") -> None:
        """切换当前对话：离开的对话启动的后台进程全部终止（新对话里的 agent 不知道它们）。"""
        if self.current and self.current is not conv:
            self.current.close()
        self.current = conv

    # ---------- 推送 ----------

    def broadcast(self, conv: Conversation, event: dict) -> None:
        """可以从任何线程调用。只推送当前显示的对话的事件。"""
        if conv is not self.current:
            return
        with self._lock:
            for q, loop in self._clients.items():
                loop.call_soon_threadsafe(q.put_nowait, event)

    def _snapshot(self) -> list[dict]:
        """浏览器重建界面需要的全部事件：清空 → 历史重放 → 当前状态。"""
        events = [{"type": "reset"}]
        if self.current:
            events += self.current.events
        return events + [self.state(), self.conversations()]

    def attach(self, q: asyncio.Queue) -> None:
        with self._lock:
            for ev in self._snapshot():
                q.put_nowait(ev)
            self._clients[q] = asyncio.get_running_loop()

    def detach(self, q: asyncio.Queue) -> None:
        with self._lock:
            self._clients.pop(q, None)

    def _push_all(self, events: list[dict]) -> None:
        with self._lock:
            for q, loop in self._clients.items():
                for ev in events:
                    loop.call_soon_threadsafe(q.put_nowait, ev)

    def push_full(self) -> None:
        self._push_all(self._snapshot())

    def push_state(self) -> None:
        self._push_all([self.state()])

    def push_meta(self) -> None:
        self._push_all([self.state(), self.conversations()])

    def state(self) -> dict:
        c = self.current
        return {
            "type": "state",
            "version": __version__,  # 前端据此发现服务升级（自动刷新）或连到了旧服务（提示）
            "demo": self.demo,
            "model": self.llm.model if self.llm else "未配置模型",
            "base_url": getattr(self.llm, "base_url", ""),
            "configured": self.llm is not None,  # 没配置时前端自动打开设置
            "auto": self.auto,
            "sandbox": bool(c.sandbox) if c else self.sandbox,
            "previews": c.sandbox.forwarder.items() if c and c.sandbox else [],
            "team": bool(c.team) if c else self.team,
            "busy": bool(c and c.busy),
            "conversation": {"id": c.id, "title": c.title, "workspace": str(c.real_root),
                             "scratch": c.scratch, "copy": str(c.shadow.copy) if c.shadow else ""} if c else None,
            "sandbox_changes": (lambda ch: {"summary": describe_changes(ch), **ch} if ch else None)(
                c.shadow_changes()) if c and c.shadow and not c.busy else None,
            "changed": sorted(c.changed_files) if c else [],
            "undo": (lambda cp: cp.label if cp else "")(c.agent.checkpoints.last()) if c else "",
            "usage": c.agent.usage if c else {"prompt": 0, "completion": 0, "cached": 0},
            "recent_workspaces": self.store.recent_workspaces(),
        }

    def conversations(self) -> dict:
        return {"type": "conversations", "items": self.store.list_conversations()}

    def notice(self, text: str, level: str = "error") -> None:
        self._push_all([{"type": "notice", "level": level, "text": text}])

    # ---------- 处理浏览器消息 ----------

    @property
    def busy(self) -> bool:
        return bool(self.current and self.current.busy)

    def handle(self, msg: dict) -> None:
        kind = msg.get("type")
        c = self.current
        if kind == "user_message":
            text = str(msg.get("text", "")).strip()
            images = msg.get("images") or []
            if not text and not images:
                return
            if not self.llm:
                return self.notice("还没有配置模型：请点右上角的 ⚙ 设置，选择服务商并填写 API Key")
            if not c:  # 没选工作区就直接提问（比如算法题）：用临时工作区
                self.open_scratch()
                c = self.current
                self.push_full()
            if c.busy:  # 运行中：作为插话交给 agent，在当前这一步结束后插入对话
                if images:
                    return self.notice("运行中补充的话只能是文字，图片请等任务结束后再发")
                return c.steer(text)
            if not isinstance(images, list) or len(images) > MAX_IMAGES:
                return self.notice(f"一次最多发送 {MAX_IMAGES} 张图片")
            try:
                image_ids = [self.store.save_image(str(url)) for url in images]
            except ValueError as e:
                return self.notice(f"图片无法使用：{e}")
            c.start(text, image_ids)
        elif kind == "permission_response" and c:
            c.ui.answer_permission(msg.get("id"), msg.get("choice"), str(msg.get("feedback", "")))
        elif kind == "undo" and c:
            if c.busy:
                return self.notice("任务运行中，请先停止再撤销")
            result = c.agent.undo(force=bool(msg.get("force")))
            if result["conflicts"] and not (result["restored"] or result["deleted"]):
                return self._push_all([{"type": "undo_conflict", "text": describe(result)}])
            c.emit({"type": "notice", "level": "info", "text": describe(result)})
            c.emit({"type": "files_changed", "changed": sorted(c.changed_files)}, log=False)
            self.push_state()
        elif kind in ("sandbox_apply", "sandbox_discard") and c and c.shadow:
            if c.busy:
                return self.notice("任务运行中，请先停止再处理沙箱里的改动")
            if kind == "sandbox_apply":
                result = c.shadow.apply()
                text = f"已把 {len(result['applied'])} 个文件的改动应用到项目"
                if result["conflicts"]:
                    text += (f"；这些文件你在项目里也改过，没有覆盖：{'、'.join(result['conflicts'])}。"
                             "可以对照副本手动合并，或者点「放弃」让副本恢复成项目现在的样子")
                c.emit({"type": "notice", "level": "warn" if result["conflicts"] else "info", "text": text})
            else:
                restored = c.shadow.discard()
                c.emit({"type": "notice", "level": "info", "text": f"已放弃沙箱里的改动（{len(restored)} 个文件恢复成项目里的样子）"})
            c.emit({"type": "files_changed", "changed": sorted(c.changed_files)}, log=False)
            c.save()
            self.push_state()
        elif kind == "cancel" and c and c.busy:
            c.agent.cancel()
        elif kind == "set_auto":
            self.auto = bool(msg.get("value"))
            if c:
                c.permissions.auto = self.auto
            self.push_meta()
        elif kind == "set_team":
            if c and c.busy:
                return self.notice("任务运行中，请先停止再切换模式")
            self.team = bool(msg.get("value"))
            if c:
                c.set_team(self.team)
                c.save()
            self.push_meta()
        elif kind in ("new_conversation", "open_conversation", "delete_conversation"):
            if self.busy:
                return self.notice("任务运行中，请先停止再切换对话")
            if kind == "new_conversation":
                path = msg.get("workspace") or (str(c.real_root) if c and not c.scratch else "")
                if msg.get("scratch"):  # 选择框里点了"不用工作区，直接提问"
                    self.open_scratch()
                    err = None
                elif path:
                    err = self.open_workspace(path)
                elif c and c.scratch:  # 临时对话里点"新对话"：再开一个临时对话
                    self.open_scratch()
                    err = None
                else:
                    err = "请先选择一个工作区"
            elif kind == "open_conversation":
                err = self.open_conversation(str(msg.get("id", "")))
            else:
                conv_id = str(msg.get("id", ""))
                self._remove_scratch_dir(conv_id)
                self._remove_shadow(conv_id)
                self.store.delete(conv_id)
                err = None
                if c and c.id == conv_id:
                    self._switch(None)
                    self.open_latest()
            if err:
                return self.notice(err)
            self.push_full()
