"""MCP 客户端：用迷你服务器测试 stdio 的握手、分页、调用、图片、错误、服务器反向请求；HTTP 传输用模拟响应测试。"""
import json
import sys
from pathlib import Path

import httpx
import pytest

from coder.mcp import HttpTransport, MCPManager, MCPServer, load_config, tool_name
from coder.permissions import PermissionManager
from coder.tools import ToolError, build_tools
from coder.workspace import Workspace

from test_agent import FakeLLM, SilentUI, reply, tool_call

FAKE = str(Path(__file__).parent / "fake_mcp_server.py")
CONFIG = {"fake": {"command": sys.executable, "args": [FAKE]}}


@pytest.fixture
def manager(tmp_path):
    m = MCPManager(tmp_path, config=CONFIG)
    m.start()
    yield m
    m.close()


def test_stdio_handshake_paging_and_calls(tmp_path, manager):
    tools = manager.tools(Workspace(tmp_path))
    assert sorted(tools) == ["mcp__fake__broken", "mcp__fake__echo", "mcp__fake__screenshot", "mcp__fake__where"]
    echo = tools["mcp__fake__echo"]
    assert echo.needs_permission and "$schema" not in echo.parameters and echo.parameters["required"] == ["text"]
    assert echo.run(text="你好") == "回声：你好"
    shot = tools["mcp__fake__screenshot"].run()
    saved = tmp_path / shot.split("图片已保存到 ")[1].rstrip("]")  # 相对工作区的路径
    assert shot.startswith("截好了") and saved.is_file() and saved.read_bytes()[:4] == b"\x89PNG"
    assert tools["mcp__fake__broken"].run().startswith("工具报告了错误：页面打不开")
    roots = json.loads(tools["mcp__fake__where"].run())  # 服务器反过来问工作区在哪
    assert roots[0]["uri"] == tmp_path.resolve().as_uri()
    status = manager.status()[0]
    assert status["state"] == "connected" and status["server"] == "fake" and len(status["tools"]) == 4


def test_agent_calls_mcp_tool_with_permission(tmp_path, manager):
    from coder.agent import Agent
    asked = []
    perms = PermissionManager(ask=lambda t, p, **k: (asked.append((t, p)), ("y", ""))[1])
    ws = Workspace(tmp_path)
    llm = FakeLLM([reply(calls=[tool_call("m", "mcp__fake__echo", text="查文档")]), reply("好了")])
    agent = Agent(llm, build_tools(ws, mcp=manager), ws, perms, SilentUI())
    assert any(s["function"]["name"] == "mcp__fake__echo" for s in agent.tool_schemas)
    agent.run("用 MCP")
    assert asked[0][0] == "mcp__fake__echo" and "MCP 服务器 fake" in asked[0][1]
    assert llm.seen[1][-1]["content"] == "回声：查文档"


def test_unknown_tool_and_failed_start(tmp_path):
    m = MCPManager(tmp_path, config={**CONFIG, "gone": {"command": "definitely-not-a-command-xyz"},
                                     "off": {"command": "x", "disabled": True}})
    m.start()
    try:
        states = {s["name"]: s["state"] for s in m.status()}
        assert states == {"fake": "connected", "gone": "error", "off": "disabled"}
        assert "启动失败" in m.describe()
        server = m.servers["fake"]
        from coder.mcp import MCPTool
        with pytest.raises(ToolError, match="unknown tool"):
            MCPTool(Workspace(tmp_path), server, {"name": "nope"}).run()
    finally:
        m.close()


def test_server_exit_is_reported(tmp_path):
    server = MCPServer("quits", {"command": sys.executable, "args": ["-c", "import sys; sys.stderr.write('boom\\n')"]},
                       tmp_path)
    with pytest.raises(Exception, match="已经退出"):
        server.start()
    server.close()


def test_config_merge_and_env(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home).mkdir()
    (home / "mcp.json").write_text(json.dumps({"mcpServers": {"a": {"command": "user-a"}, "b": {"command": "user-b"}}}),
                                   encoding="utf-8")
    (tmp_path / ".coder").mkdir()
    (tmp_path / ".coder" / "mcp.json").write_text(json.dumps({"mcpServers": {"a": {"command": "project-a"}}}),
                                                  encoding="utf-8")
    monkeypatch.setenv("CODER_HOME", str(home))
    assert load_config(tmp_path) == {"a": {"command": "project-a"}, "b": {"command": "user-b"}}
    assert tool_name("my server", "do.thing") == "mcp__my_server__do_thing"


def test_http_transport_json_and_sse():
    """Streamable HTTP：握手返回 JSON 并给出会话编号，之后的请求带上它；工具调用的响应是 SSE 流。"""
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        msg = json.loads(request.content)
        seen.append((msg.get("method"), request.headers.get("mcp-session-id"), request.headers.get("authorization")))
        if msg.get("method") == "initialize":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": msg["id"], "result": {
                "protocolVersion": "2025-06-18", "serverInfo": {"name": "web"}}}, headers={"Mcp-Session-Id": "s1"})
        if "id" not in msg:
            return httpx.Response(202)
        if msg["method"] == "tools/list":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": msg["id"], "result": {"tools": [
                {"name": "search", "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}}}]}})
        body = (f'event: message\ndata: {{"jsonrpc":"2.0","method":"notifications/progress","params":{{}}}}\n\n'
                f'data: {{"jsonrpc":"2.0","id":{msg["id"]},"result":{{"content":[{{"type":"text","text":"结果"}}]}}}}\n\n')
        return httpx.Response(200, content=body.encode(), headers={"content-type": "text/event-stream"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    factory = lambda name, spec, root, on_message: HttpTransport(name, spec, root, on_message, client=client)
    server = MCPServer("web", {"type": "http", "url": "http://mcp.test/mcp", "headers": {"Authorization": "Bearer t"}},
                       ".", transport_factory=factory)
    server.start()
    assert [t["name"] for t in server.tools] == ["search"]
    assert server.call("search", {"q": "x"})["content"][0]["text"] == "结果"
    assert seen[0] == ("initialize", None, "Bearer t")
    assert all(sid == "s1" for _, sid, _ in seen[1:])  # 握手之后都带着会话编号
