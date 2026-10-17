"""后台进程：开发服务器、监听编译这类不会自己退出的命令。

run_command 等命令结束才返回，遇到永不退出的进程只能超时。这里的工具在后台启动进程、随时读取新的输出、
结束时连同子进程一起终止（shell=True 时真正的程序是 shell 的子进程，只杀 shell 会留下孤儿进程）。
"""
import atexit
import itertools
import re
import subprocess
import threading
import time

from .base import Tool, ToolError
from .shell import LOCAL, NETWORK_PARAM, check_dangerous, decode

MAX_RUNNING = 5            # 同时运行的后台进程上限
BUFFER_BYTES = 1_000_000   # 每个进程最多保留最近 1MB 输出
OUTPUT_CHARS = 8000        # 一次最多返回的输出字符数（保留最新的部分）
MAX_WAIT = 60


def decode_partial(data: bytes) -> tuple[str, int]:
    """解码一段可能在多字节字符中间截断的输出，返回 (文本, 实际用掉的字节数)。"""
    try:
        return data.decode("utf-8"), len(data)
    except UnicodeDecodeError as e:
        if e.start >= len(data) - 3 and e.reason == "unexpected end of data":
            return data[:e.start].decode("utf-8", errors="replace"), e.start
        return decode(data), len(data)  # 不是 UTF-8（比如 Windows 上的 GBK 输出）


class BackgroundProcess:
    def __init__(self, pid_label: str, command: str, cwd, executor=LOCAL, network: bool = False):
        self.id, self.command, self.executor = pid_label, command, executor
        self.started = time.time()
        self.proc = executor.popen(command, cwd, network=network)
        self.buffer = bytearray()
        self.dropped = 0          # 因为超过缓冲上限丢掉的字节数
        self.cursor = 0           # 已经返回给模型的位置（按总字节数计）
        self.eof = False          # 输出已经读完（进程结束）
        self.lock = threading.Lock()
        self.changed = threading.Condition(self.lock)
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        stream = self.proc.stdout
        while True:
            chunk = stream.read1(65536) if hasattr(stream, "read1") else stream.read(4096)
            with self.changed:
                if chunk:
                    self.buffer += chunk
                    if len(self.buffer) > BUFFER_BYTES:
                        cut = len(self.buffer) - BUFFER_BYTES
                        del self.buffer[:cut]
                        self.dropped += cut
                else:
                    self.eof = True
                self.changed.notify_all()
            if not chunk:
                break
        try:
            self.proc.wait(10)
        except subprocess.TimeoutExpired:
            return
        self.executor.finished(self.proc)  # 沙箱：进程结束后归还网络

    @property
    def total(self) -> int:
        return self.dropped + len(self.buffer)

    def status(self) -> str:
        code = self.proc.poll()
        return "运行中" if code is None else f"已退出（退出码 {code}）"

    def wait(self, seconds: float, pattern: str | None = None) -> bool:
        """等待：进程退出、新输出里出现 pattern（如 "Running on"），或时间到。返回 pattern 是否出现。"""
        regex = re.compile(pattern) if pattern else None
        deadline = time.time() + seconds
        with self.changed:
            while True:
                if regex and regex.search(self._text_since(self.cursor)):
                    return True
                if self.eof:  # 输出关闭通常意味着进程结束了，稍等它真正退出，好报告退出码
                    try:
                        self.proc.wait(max(0.1, min(deadline - time.time(), 2)))
                    except subprocess.TimeoutExpired:
                        pass
                    return False
                left = deadline - time.time()
                if left <= 0:
                    return False
                self.changed.wait(min(left, 0.2))

    def _text_since(self, pos: int) -> str:
        start = max(pos, self.dropped) - self.dropped
        return decode(bytes(self.buffer[start:]))

    def read_new(self) -> str:
        """取出上次读取之后的新输出。"""
        with self.lock:
            skipped = max(0, self.dropped - self.cursor)
            start = max(self.cursor, self.dropped) - self.dropped
            data = bytes(self.buffer[start:])
            text, used = (decode(data), len(data)) if self.eof else decode_partial(data)
            self.cursor = self.dropped + start + used
        note = f"[前面有 {skipped} 字节输出超出缓冲区已丢弃]\n" if skipped else ""
        if len(text) > OUTPUT_CHARS:
            note += f"[新输出共 {len(text)} 字符，只显示最后 {OUTPUT_CHARS} 字符]\n"
            text = text[-OUTPUT_CHARS:]
        return note + text


_managers: "set[ProcessManager]" = set()  # 启动过进程的管理器（强引用：会话对象被回收后，退出时也要能找到）


class ProcessManager:
    """一个会话里 agent 启动的后台进程。会话结束（关闭对话、退出程序）时全部终止。"""

    def __init__(self, executor=None):
        self.executor = executor or LOCAL  # 本机，或者沙箱容器
        self.procs: dict[str, BackgroundProcess] = {}
        self._ids = itertools.count(1)
        self.lock = threading.Lock()

    def start(self, command: str, cwd, network: bool = False) -> BackgroundProcess:
        with self.lock:
            running = [p for p in self.procs.values() if p.proc.poll() is None]
            if len(running) >= MAX_RUNNING:
                raise ToolError(f"已经有 {len(running)} 个后台进程在运行（上限 {MAX_RUNNING}），"
                                "请先用 stop_process 停掉不需要的")
            p = BackgroundProcess(f"p{next(self._ids)}", command, cwd, self.executor, network)
            self.procs[p.id] = p
            _managers.add(self)
            return p

    def get(self, pid: str) -> BackgroundProcess:
        if pid not in self.procs:
            known = "、".join(self.procs) or "无"
            raise ToolError(f"没有后台进程 {pid}（现有：{known}）")
        return self.procs[pid]

    def stop(self, pid: str) -> BackgroundProcess:
        p = self.get(pid)
        self.executor.kill(p.proc)
        return p

    def stop_all(self) -> int:
        """终止所有还在运行的进程，返回终止的个数。"""
        n = 0
        for p in list(self.procs.values()):
            if p.proc.poll() is None:
                self.executor.kill(p.proc)
                n += 1
        return n

    def running(self) -> list[BackgroundProcess]:
        return [p for p in self.procs.values() if p.proc.poll() is None]


@atexit.register
def _cleanup() -> None:  # 兜底：程序退出时不留下孤儿进程
    for m in list(_managers):
        m.stop_all()


def _report(p: BackgroundProcess, output: str) -> str:
    text = f"进程 {p.id}：{p.status()}\n$ {p.command}\n--- 输出 ---\n{output.strip() or '(暂无输出)'}"
    forwarder = getattr(p.executor, "forwarder", None)  # 沙箱：开发服务器的端口转发到本机
    if forwarder:
        try:
            notes = forwarder.sync()
        except Exception:
            notes = []
        if notes:
            text += "\n\n[端口预览]\n" + "\n".join(notes)
    return text


class StartProcess(Tool):
    name = "start_process"
    description = (
        "在后台启动一个长时间运行的命令（开发服务器、watch 编译、需要一直运行的服务等），立即返回进程编号和最初几秒的输出。"
        "之后用 process_output 查看新输出，用 stop_process 停止。普通的、会自己结束的命令请用 run_command。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "要执行的命令"},
            "wait": {"type": "integer", "description": "返回前最多等待几秒收集输出，默认 3，最大 60", "default": 3},
            "wait_for": {"type": "string",
                         "description": "可选：输出里出现这个正则时立即返回，例如 \"Running on|Listening\""},
        },
        "required": ["command"],
    }
    needs_permission = True

    def __init__(self, workspace, manager: ProcessManager):
        super().__init__(workspace)
        self.manager = manager
        if manager.executor.supports_network:  # 沙箱模式：多一个 network 参数
            self.parameters = {**self.parameters,
                               "properties": {**self.parameters["properties"], "network": NETWORK_PARAM}}

    def preview(self, command: str, wait: int = 3, wait_for: str | None = None, network: bool = False) -> str:
        check_dangerous(command)
        where = "后台运行" + ("，沙箱" if self.manager.executor.supports_network else "") + ("，联网" if network else "")
        return f"$ {command}    （{where}）"

    def run(self, command: str, wait: int = 3, wait_for: str | None = None, network: bool = False) -> str:
        check_dangerous(command)
        if wait_for:
            try:
                re.compile(wait_for)
            except re.error as e:
                raise ToolError(f"wait_for 不是合法的正则：{e}")
        p = self.manager.start(command, self.ws.root, network)
        matched = p.wait(max(0, min(wait, MAX_WAIT)), wait_for)
        out = _report(p, p.read_new())
        if wait_for and not matched and p.proc.poll() is None:
            out += f"\n\n[等待 {wait} 秒还没出现 {wait_for!r}，进程仍在运行，可以稍后用 process_output 再看]"
        return out


class ProcessOutput(Tool):
    name = "process_output"
    description = "查看后台进程上次查看之后的新输出和运行状态。可以等待几秒，或等到输出里出现指定内容。"
    parameters = {
        "type": "object",
        "properties": {
            "id": {"type": "string", "description": "进程编号，如 p1"},
            "wait": {"type": "integer", "description": "最多等待几秒，默认 0（立即返回），最大 60", "default": 0},
            "wait_for": {"type": "string", "description": "可选：输出里出现这个正则时立即返回"},
        },
        "required": ["id"],
    }

    def __init__(self, workspace, manager: ProcessManager):
        super().__init__(workspace)
        self.manager = manager

    def run(self, id: str, wait: int = 0, wait_for: str | None = None) -> str:
        p = self.manager.get(id)
        if wait > 0:
            p.wait(min(wait, MAX_WAIT), wait_for)
        return _report(p, p.read_new())


class StopProcess(Tool):
    name = "stop_process"
    description = "停止一个后台进程（连同它启动的子进程），返回最后的输出。"
    parameters = {
        "type": "object",
        "properties": {"id": {"type": "string", "description": "进程编号，如 p1"}},
        "required": ["id"],
    }

    def __init__(self, workspace, manager: ProcessManager):
        super().__init__(workspace)
        self.manager = manager

    def run(self, id: str) -> str:
        p = self.manager.stop(id)
        p.wait(1)  # 让最后的输出读完
        return _report(p, p.read_new())


class ListProcesses(Tool):
    name = "list_processes"
    description = "列出本次会话启动的后台进程及其状态。"

    def __init__(self, workspace, manager: ProcessManager):
        super().__init__(workspace)
        self.manager = manager

    def run(self) -> str:
        if not self.manager.procs:
            return "没有后台进程"
        now = time.time()
        return "\n".join(f"{p.id} [{p.status()}] 已运行 {int(now - p.started)} 秒：{p.command}"
                         for p in self.manager.procs.values())


PROCESS_TOOLS = [StartProcess, ProcessOutput, StopProcess, ListProcesses]
