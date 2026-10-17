"""MCP（Model Context Protocol）客户端：把外部 MCP 服务器提供的工具接进 agent。

自己实现协议，不依赖官方 SDK：JSON-RPC 2.0，支持两种传输
- stdio：启动服务器进程，每行一条 JSON 消息（大多数服务器，比如 fetch、Playwright）
- Streamable HTTP：向一个 URL POST JSON-RPC，响应可能是 JSON，也可能是 SSE 流

配置用通用的 mcpServers 格式，读取顺序：项目的 .coder/mcp.json、~/.coder/mcp.json（同名的项目优先）：

    {"mcpServers": {
        "fetch": {"command": "python", "args": ["-m", "mcp_server_fetch"]},
        "docs":  {"type": "http", "url": "http://127.0.0.1:9000/mcp", "headers": {"Authorization": "Bearer ${TOKEN}"}},
        "slow":  {"command": "npx", "args": ["-y", "some-server"], "disabled": true}
    }}

服务器的每个工具变成 agent 的一个工具，名字是 mcp__服务器名__工具名，调用前和写文件一样需要用户确认。
服务器在本机运行（不在沙箱里）：它们是用户自己配置、信任的程序。
"""
import atexit
import base64
import itertools
import json
import os
import re
import shutil
import subprocess
import threading
import time
from collections import deque
from pathlib import Path

import httpx

from . import __version__
from .tools.base import Tool, ToolError

PROTOCOL_VERSION = "2025-06-18"
REQUEST_TIMEOUT = 60      # 一次请求最多等多久（秒）；浏览器类工具可能较慢
START_TIMEOUT = 60        # 启动 + 握手最多等多久（第一次用 npx / uvx 可能要下载）
MAX_RESULT_CHARS = 30_000


class MCPError(Exception):
    pass


def config_files(root: str | Path) -> list[Path]:
    home = Path(os.getenv("CODER_HOME") or Path.home() / ".coder")
    return [Path(root) / ".coder" / "mcp.json", home / "mcp.json"]


def load_config(root: str | Path) -> dict[str, dict]:
    """合并项目和用户的配置，同名的以项目为准。"""
    servers: dict[str, dict] = {}
    for path in reversed(config_files(root)):  # 先读用户的，再用项目的覆盖
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except ValueError as e:
                raise MCPError(f"{path} 不是合法的 JSON：{e}")
            servers.update(data.get("mcpServers", {}))
    return servers


def expand(value: str) -> str:
    """配置里的 ${VAR} 换成环境变量（密钥不用写进配置文件）。"""
    return re.sub(r"\$\{(\w+)\}", lambda m: os.environ.get(m.group(1), ""), value)


def tool_name(server: str, name: str) -> str:
    """OpenAI 的函数名只能是字母、数字、_、-，最长 64 个字符。"""
    raw = f"mcp__{server}__{name}"
    return re.sub(r"[^A-Za-z0-9_-]", "_", raw)[:64]


# ---------- 传输 ----------

class StdioTransport:
    """启动服务器进程，按行收发 JSON-RPC 消息。"""

    def __init__(self, name: str, spec: dict, root: Path, on_message):
        command = shutil.which(spec["command"]) or spec["command"]  # Windows 上 npx 是 npx.cmd
        # MCP 要求 UTF-8。Python 写的服务器在中文 Windows 上默认按 GBK 输出（stdout 跟随系统代码页），
        # 客户端按 UTF-8 解析就会失败；让它用 UTF-8（配置里明确写了的以配置为准）
        env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
               **{k: expand(str(v)) for k, v in spec.get("env", {}).items()}}
        self.name, self.on_message = name, on_message
        self.stderr: deque[str] = deque(maxlen=50)  # 最近的错误输出，出问题时给用户看
        try:
            self.proc = subprocess.Popen(
                [command, *[expand(str(a)) for a in spec.get("args", [])]], cwd=spec.get("cwd") or root, env=env,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}))
        except OSError as e:
            raise MCPError(f"启动失败（{spec['command']}）：{e}")
        self.lock = threading.Lock()
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=self._read_err, daemon=True).start()

    def _read(self) -> None:
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                self.on_message(json.loads(line))
            except ValueError:
                self.stderr.append(f"无法解析的输出：{line[:200]!r}")
        self.on_message(None)  # 进程退出

    def _read_err(self) -> None:
        for line in self.proc.stderr:
            self.stderr.append(line.decode("utf-8", errors="replace").rstrip())

    def send(self, message: dict) -> None:
        data = (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")
        with self.lock:
            try:
                self.proc.stdin.write(data)
                self.proc.stdin.flush()
            except OSError as e:
                raise MCPError(f"服务器 {self.name} 已经退出：{self.last_error() or e}")

    def last_error(self) -> str:
        return "\n".join(list(self.stderr)[-5:])

    def close(self) -> None:
        if self.proc.poll() is None:
            try:
                self.proc.stdin.close()  # 按协议先关输入，给服务器机会自己退出
                self.proc.wait(2)
            except (OSError, subprocess.TimeoutExpired):
                from .tools.shell import kill_tree
                kill_tree(self.proc)


class HttpTransport:
    """Streamable HTTP：每条消息 POST 到同一个 URL；响应是 JSON，或者是 SSE 流（里面有我们要的那条响应）。"""

    def __init__(self, name: str, spec: dict, root: Path, on_message, client: httpx.Client | None = None):
        self.name, self.url, self.on_message = name, spec["url"], on_message
        self.headers = {k: expand(str(v)) for k, v in spec.get("headers", {}).items()}
        self.client = client or httpx.Client(timeout=httpx.Timeout(REQUEST_TIMEOUT, connect=10))
        self.session_id: str | None = None
        self.protocol: str | None = None

    def send(self, message: dict) -> None:
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                   **self.headers}
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        if self.protocol:
            headers["MCP-Protocol-Version"] = self.protocol
        try:
            with self.client.stream("POST", self.url, json=message, headers=headers) as r:
                if r.status_code >= 400:
                    raise MCPError(f"服务器 {self.name} 返回 HTTP {r.status_code}：{r.read().decode(errors='replace')[:300]}")
                self.session_id = r.headers.get("mcp-session-id", self.session_id)
                kind = r.headers.get("content-type", "")
                if "text/event-stream" in kind:
                    data: list[str] = []
                    for line in r.iter_lines():
                        if line.startswith("data:"):
                            data.append(line[5:].strip())
                        elif not line and data:  # 一个事件结束
                            self.on_message(json.loads("\n".join(data)))
                            data = []
                    if data:
                        self.on_message(json.loads("\n".join(data)))
                elif "json" in kind:
                    body = json.loads(r.read() or b"null")
                    for m in body if isinstance(body, list) else [body]:
                        if m:
                            self.on_message(m)
        except httpx.ConnectError:
            raise MCPError(f"连不上 {self.url}（MCP 服务器没有启动，或者地址不对）")
        except httpx.HTTPError as e:
            raise MCPError(f"连接服务器 {self.name} 失败：{e}")

    def last_error(self) -> str:
        return ""

    def close(self) -> None:
        if self.session_id:  # 告诉服务器会话结束
            try:
                self.client.delete(self.url, headers={"Mcp-Session-Id": self.session_id, **self.headers}, timeout=5)
            except httpx.HTTPError:
                pass
        self.client.close()


# ---------- 会话 ----------

class MCPServer:
    """和一个 MCP 服务器的连接：握手、列工具、调用工具。"""

    def __init__(self, name: str, spec: dict, root: str | Path, transport_factory=None):
        self.name, self.spec, self.root = name, spec, Path(root).resolve()
        self.ids = itertools.count(1)
        self.pending: dict[int, dict] = {}
        self.cond = threading.Condition()
        self.closed = False
        self.tools: list[dict] = []
        self.info: dict = {}
        self.instructions = ""
        self.tools_changed = False
        factory = transport_factory or (HttpTransport if spec.get("type") in ("http", "streamable-http") or "url" in spec
                                        else StdioTransport)
        self.transport = factory(name, spec, self.root, self._on_message)

    # 收到消息：响应交给等待的请求；服务器发来的请求（比如 roots/list）在这里回答
    def _on_message(self, msg: dict | None) -> None:
        if msg is None:
            with self.cond:
                self.closed = True
                self.cond.notify_all()
            return
        if "method" in msg:
            if "id" in msg:
                self._answer(msg)
            elif msg["method"] == "notifications/tools/list_changed":
                self.tools_changed = True
            return
        with self.cond:
            if msg.get("id") in self.pending:
                self.pending[msg["id"]]["response"] = msg
                self.cond.notify_all()

    def _answer(self, req: dict) -> None:
        if req["method"] == "roots/list":  # 告诉服务器工作区在哪（文件类服务器会用到）
            result = {"roots": [{"uri": self.root.as_uri(), "name": self.root.name}]}
            reply = {"jsonrpc": "2.0", "id": req["id"], "result": result}
        elif req["method"] == "ping":
            reply = {"jsonrpc": "2.0", "id": req["id"], "result": {}}
        else:
            reply = {"jsonrpc": "2.0", "id": req["id"], "error": {"code": -32601, "message": "not supported"}}
        threading.Thread(target=self._safe_send, args=(reply,), daemon=True).start()

    def _safe_send(self, msg: dict) -> None:
        try:
            self.transport.send(msg)
        except MCPError:
            pass

    def request(self, method: str, params: dict | None = None, timeout: float = REQUEST_TIMEOUT) -> dict:
        rid = next(self.ids)
        slot: dict = {}
        with self.cond:
            self.pending[rid] = slot
        try:
            self.transport.send({"jsonrpc": "2.0", "id": rid, "method": method, **({"params": params} if params else {})})
            deadline = time.time() + timeout
            with self.cond:
                while "response" not in slot:
                    if self.closed:
                        raise MCPError(f"服务器 {self.name} 已经退出" + (f"：{self.transport.last_error()}"
                                                                     if self.transport.last_error() else ""))
                    left = deadline - time.time()
                    if left <= 0:
                        raise MCPError(f"服务器 {self.name} 超过 {timeout:.0f} 秒没有响应（{method}）")
                    self.cond.wait(min(left, 0.5))
        finally:
            with self.cond:
                self.pending.pop(rid, None)
        resp = slot["response"]
        if "error" in resp:
            err = resp["error"]
            raise MCPError(f"{method} 失败：{err.get('message')}（{err.get('code')}）")
        return resp.get("result") or {}

    def notify(self, method: str) -> None:
        self.transport.send({"jsonrpc": "2.0", "method": method})

    def start(self) -> None:
        result = self.request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"roots": {"listChanged": False}},
            "clientInfo": {"name": "coder", "version": __version__},
        }, timeout=START_TIMEOUT)
        self.info = result.get("serverInfo", {})
        self.instructions = result.get("instructions", "")
        if isinstance(self.transport, HttpTransport):
            self.transport.protocol = result.get("protocolVersion", PROTOCOL_VERSION)
        self.notify("notifications/initialized")
        self.refresh_tools()

    def refresh_tools(self) -> None:
        tools, cursor = [], None
        while True:
            result = self.request("tools/list", {"cursor": cursor} if cursor else None)
            tools += result.get("tools", [])
            cursor = result.get("nextCursor")
            if not cursor:
                break
        self.tools, self.tools_changed = tools, False

    def call(self, name: str, arguments: dict) -> dict:
        return self.request("tools/call", {"name": name, "arguments": arguments})

    def close(self) -> None:
        self.closed = True
        self.transport.close()


def render_result(result: dict, server: str, save_dir: Path | None, root: Path | None = None) -> str:
    """把工具结果转成给模型看的文字。图片存成文件（不是所有模型都能看图），文字里写上路径。"""
    parts = []
    for item in result.get("content", []):
        kind = item.get("type")
        if kind == "text":
            parts.append(item.get("text", ""))
        elif kind == "image" and save_dir is not None:
            ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}.get(item.get("mimeType"), "png")
            save_dir.mkdir(parents=True, exist_ok=True)
            path = save_dir / f"{server}-{time.strftime('%H%M%S')}-{len(parts)}.{ext}"
            path.write_bytes(base64.b64decode(item.get("data", "")))
            shown = path.relative_to(root).as_posix() if root and path.is_relative_to(root) else path.as_posix()
            parts.append(f"[图片已保存到 {shown}]")
        elif kind == "resource":
            res = item.get("resource", {})
            parts.append(res.get("text") or f"[资源 {res.get('uri')}]")
        elif kind == "resource_link":
            parts.append(f"[资源链接 {item.get('uri')}：{item.get('name', '')}]")
    if not parts and result.get("structuredContent") is not None:
        parts.append(json.dumps(result["structuredContent"], ensure_ascii=False, indent=1))
    text = "\n".join(parts) or "(没有返回内容)"
    if result.get("isError"):
        text = "工具报告了错误：" + text
    if len(text) > MAX_RESULT_CHARS:
        text = text[:MAX_RESULT_CHARS] + f"\n...（结果共 {len(text)} 字符，只显示前 {MAX_RESULT_CHARS}）"
    return text


class MCPTool(Tool):
    """把一个 MCP 工具包装成 agent 的工具。"""
    needs_permission = True  # 外部工具可能联网、操作浏览器，默认每次确认（可以选"总是允许"）

    def __init__(self, workspace, server: MCPServer, spec: dict):
        super().__init__(workspace)
        self.server, self.remote = server, spec["name"]
        self.name = tool_name(server.name, spec["name"])
        desc = spec.get("description") or spec.get("title") or spec["name"]
        self.description = f"[MCP 服务器 {server.name}] {desc}"[:1024]
        schema = {k: v for k, v in (spec.get("inputSchema") or {}).items() if k != "$schema"}
        self.parameters = {"type": "object", "properties": {}, **schema}

    def preview(self, **kwargs) -> str:
        args = json.dumps(kwargs, ensure_ascii=False, indent=1)
        return f"MCP 服务器 {self.server.name} 的工具 {self.remote}\n参数：{args[:2000]}"

    def run(self, **kwargs) -> str:
        try:
            result = self.server.call(self.remote, kwargs)
        except MCPError as e:
            raise ToolError(str(e))
        return render_result(result, self.server.name, self.ws.root / ".coder" / "mcp-files", self.ws.root)


class MCPManager:
    """一个会话里连接的 MCP 服务器。会话结束（关闭对话、退出程序）时全部关闭。"""

    def __init__(self, root: str | Path, config: dict[str, dict] | None = None):
        self.root = Path(root).resolve()
        self.config = load_config(self.root) if config is None else config
        self.servers: dict[str, MCPServer] = {}
        self.errors: dict[str, str] = {}  # 启动失败的服务器和原因
        _managers.add(self)

    def start(self, on_progress=None) -> None:
        """并行启动所有没有禁用的服务器（每个最多等 START_TIMEOUT 秒）。启动失败的记下原因，不影响其他的。"""
        def one(name: str, spec: dict) -> None:
            try:
                server = MCPServer(name, spec, self.root)
                try:
                    server.start()
                except Exception:
                    server.close()
                    raise
                self.servers[name] = server
            except Exception as e:
                self.errors[name] = str(e)
            if on_progress:
                on_progress(name)

        threads = [threading.Thread(target=one, args=(n, s), daemon=True)
                   for n, s in self.config.items() if not s.get("disabled")]
        for t in threads:
            t.start()
        for t in threads:
            t.join(START_TIMEOUT + 5)

    def tools(self, workspace) -> dict[str, Tool]:
        out: dict[str, Tool] = {}
        for server in self.servers.values():
            if server.tools_changed:
                try:
                    server.refresh_tools()
                except MCPError:
                    pass
            for spec in server.tools:
                tool = MCPTool(workspace, server, spec)
                out[tool.name] = tool
        return out

    def status(self) -> list[dict]:
        rows = []
        for name, spec in self.config.items():
            if spec.get("disabled"):
                rows.append({"name": name, "state": "disabled", "tools": []})
            elif name in self.servers:
                s = self.servers[name]
                rows.append({"name": name, "state": "connected", "tools": [t["name"] for t in s.tools],
                             "server": s.info.get("name", ""), "version": s.info.get("version", "")})
            else:
                rows.append({"name": name, "state": "error", "error": self.errors.get(name, "未启动"), "tools": []})
        return rows

    def describe(self) -> str:
        rows = self.status()
        if not rows:
            return "没有配置 MCP 服务器（在 .coder/mcp.json 或 ~/.coder/mcp.json 里添加）"
        lines = []
        for r in rows:
            if r["state"] == "connected":
                lines.append(f"{r['name']}：已连接，{len(r['tools'])} 个工具（{', '.join(r['tools'][:8])}"
                             f"{'…' if len(r['tools']) > 8 else ''}）")
            elif r["state"] == "disabled":
                lines.append(f"{r['name']}：已禁用")
            else:
                lines.append(f"{r['name']}：启动失败：{r['error']}")
        return "\n".join(lines)

    def close(self) -> None:
        for server in list(self.servers.values()):
            try:
                server.close()
            except Exception:
                pass
        self.servers.clear()
        _managers.discard(self)


_managers: "set[MCPManager]" = set()


@atexit.register
def _cleanup() -> None:  # 程序退出时关闭所有服务器进程
    for m in list(_managers):
        m.close()
