"""Web 层测试：用演示模型跑完整流程，验证事件流、权限交互、对话持久化和文件接口。"""
import pytest
from fastapi.testclient import TestClient

from coder.demo import DemoLLM
from coder.store import Store
from coder.web.server import create_app
from coder.web.session import Hub


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "home")


@pytest.fixture
def ws_dir(tmp_path):
    d = tmp_path / "proj"
    d.mkdir()
    return d


def make_client(store, workspace=None, auto=True):
    hub = Hub(DemoLLM(delay=0), store, auto=auto)
    if workspace:
        assert hub.open_workspace(str(workspace)) is None
    return TestClient(create_app(hub)), hub


def drain_snapshot(ws):
    """连接后服务器先发：reset → 历史事件 → state → conversations。"""
    events = []
    while True:
        ev = ws.receive_json()
        events.append(ev)
        if ev["type"] == "conversations":
            return events


def collect_until_done(ws, on_permission=None):
    events = []
    while True:
        ev = ws.receive_json()
        events.append(ev)
        if ev["type"] == "permission_request" and on_permission:
            ws.send_json(on_permission(ev))
        if ev["type"] == "done":
            return events


def run_task(ws, text="写个 hello", on_permission=None):
    ws.send_json({"type": "user_message", "text": text})
    events = collect_until_done(ws, on_permission)
    while ws.receive_json()["type"] != "conversations":  # 任务结束后还会推送 state 和对话列表
        pass
    return events


def test_full_run_with_streaming(store, ws_dir):
    client, _ = make_client(store, ws_dir)
    with client.websocket_connect("/ws") as ws:
        drain_snapshot(ws)
        events = run_task(ws)
    types = [e["type"] for e in events]
    assert types.count("tool_call") == 5
    assert "delta" in types                     # 有流式片段
    final = [e for e in events if e["type"] == "assistant"][-1]
    assert final["reasoning"] and "完成" in final["text"]
    results = [e for e in events if e["type"] == "tool_result"]
    assert not any(r["is_error"] for r in results)
    assert "你好" in (ws_dir / "hello.py").read_text(encoding="utf-8")


def test_permission_allow_and_deny(store, ws_dir):
    client, _ = make_client(store, ws_dir, auto=False)
    answers = iter(["y", "n"])  # 允许创建文件，拒绝运行命令

    def answer(ev):
        return {"type": "permission_response", "id": ev["id"], "choice": next(answers, "y"),
                "feedback": "先别运行"}

    with client.websocket_connect("/ws") as ws:
        drain_snapshot(ws)
        events = run_task(ws, on_permission=answer)
    resolved = [e["choice"] for e in events if e["type"] == "permission_resolved"]
    assert resolved[:2] == ["y", "n"]
    denied = [e for e in events if e["type"] == "tool_result" and "用户拒绝" in e["result"]]
    assert denied and "先别运行" in denied[0]["result"]


def test_cancel_while_waiting_for_permission(store, ws_dir):
    client, hub = make_client(store, ws_dir, auto=False)
    with client.websocket_connect("/ws") as ws:
        drain_snapshot(ws)
        events = run_task(ws, on_permission=lambda ev: {"type": "cancel"})
    assert any(e["type"] == "notice" and e["text"] == "已停止" for e in events)
    assert not (ws_dir / "hello.py").exists()
    msgs = hub.current.agent.messages
    calls = {c["id"] for m in msgs if m["role"] == "assistant" for c in m.get("tool_calls", [])}
    answered = {m["tool_call_id"] for m in msgs if m["role"] == "tool"}
    assert calls == answered  # 中断后历史被修复


def test_no_workspace_uses_a_scratch_workspace(store):
    """不选工作区直接提问（比如算法题）：自动用临时工作区，不进"最近使用"；删除对话时临时目录一起删。"""
    client, hub = make_client(store)
    with client.websocket_connect("/ws") as ws:
        snap = drain_snapshot(ws)
        assert [e for e in snap if e["type"] == "state"][0]["conversation"] is None
        ws.send_json({"type": "new_conversation", "workspace": "Z:/definitely/not/here"})
        assert "不存在" in ws.receive_json()["text"]
        events = run_task(ws, "两数之和怎么做")
    c = hub.current
    assert c.scratch and c.workspace.root.parent == (store.home / "scratch").resolve()
    assert any(e["type"] == "done" for e in events) and store.recent_workspaces() == []
    assert "Scratch mode" in c.agent.messages[0]["content"]
    assert store.list_conversations()[0]["scratch"] is True
    root = c.workspace.root
    hub.handle({"type": "delete_conversation", "id": c.id})
    assert not root.exists()


def test_conversation_persisted_and_restored(store, ws_dir):
    client, _ = make_client(store, ws_dir)
    with client.websocket_connect("/ws") as ws:
        drain_snapshot(ws)
        run_task(ws, "写一个 hello 程序")
    items = store.list_conversations()
    assert len(items) == 1 and items[0]["title"] == "写一个 hello 程序"
    assert store.recent_workspaces() == [str(ws_dir.resolve())]

    # 模拟重启服务：新的 Hub 打开最近的对话，历史和 agent 上下文都恢复
    hub2 = Hub(DemoLLM(delay=0), store)
    hub2.open_latest()
    assert hub2.current.id == items[0]["id"]
    assert any(e["type"] == "tool_call" for e in hub2.current.events)
    assert len(hub2.current.agent.messages) > 5
    assert hub2.current.agent.usage["prompt"] > 0


def test_switch_new_and_delete_conversations(store, ws_dir):
    client, hub = make_client(store, ws_dir)
    with client.websocket_connect("/ws") as ws:
        drain_snapshot(ws)
        run_task(ws, "第一个")
        first_id = hub.current.id
        ws.send_json({"type": "new_conversation"})            # 沿用当前工作区
        snap = drain_snapshot(ws)
        assert snap[0]["type"] == "reset" and hub.current.id != first_id
        run_task(ws, "第二个")
        assert len(store.list_conversations()) == 2

        ws.send_json({"type": "open_conversation", "id": first_id})
        snap = drain_snapshot(ws)
        assert {"type": "user", "text": "第一个"} in snap

        ws.send_json({"type": "delete_conversation", "id": first_id})
        drain_snapshot(ws)
        assert [c["title"] for c in store.list_conversations()] == ["第二个"]
        assert hub.current.title == "第二个"  # 删除当前对话后自动打开最近的另一个


def test_reconnect_replays_history(store, ws_dir):
    client, _ = make_client(store, ws_dir)
    with client.websocket_connect("/ws") as ws:
        drain_snapshot(ws)
        run_task(ws)
    with client.websocket_connect("/ws") as ws:
        snap = drain_snapshot(ws)
    assert snap[0] == {"type": "reset"} and snap[1] == {"type": "user", "text": "写个 hello"}
    assert not any(e["type"] == "delta" for e in snap)  # 流式片段不重放


def test_store_rejects_bad_ids(store):
    assert store.load("../../etc/passwd") is None
    store.delete("../x")  # 不报错也不删东西


def test_file_api(store, ws_dir):
    (ws_dir / "src").mkdir()
    (ws_dir / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (ws_dir / "node_modules").mkdir()
    (ws_dir / "node_modules" / "junk.js").write_text("", encoding="utf-8")
    client, _ = make_client(store, ws_dir)
    assert client.get("/api/files").json()["files"] == ["src/a.py"]
    assert client.get("/api/file", params={"path": "src/a.py"}).json()["content"] == "x = 1\n"
    assert client.get("/api/file", params={"path": "../secret"}).status_code == 403


@pytest.mark.parametrize("path", ["/", "/static/app.js", "/static/style.css"])
def test_static(store, path):
    client, _ = make_client(store)
    assert client.get(path).status_code == 200


PNG_1PX = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQ"
           "DwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


def test_send_images_saved_shown_and_passed_to_model(store, ws_dir):
    client, hub = make_client(store, ws_dir)
    with client.websocket_connect("/ws") as ws:
        drain_snapshot(ws)
        ws.send_json({"type": "user_message", "text": "看图写代码", "images": [PNG_1PX]})
        events = collect_until_done(ws)
    user_ev = [e for e in events if e["type"] == "user"][0]
    image_id = user_ev["images"][0]
    assert "base64" not in str(user_ev)                       # 事件里只有 id
    assert client.get(f"/api/image/{image_id}").status_code == 200
    # 模型收到的是多模态内容
    first_user = [m for m in hub.current.agent.messages if m["role"] == "user"][0]
    assert first_user["content"][1]["image_url"]["url"] == PNG_1PX
    # 保存到磁盘时换成引用，重新打开时还原
    saved = store.load(hub.current.id)
    assert "base64" not in str(saved["messages"])
    hub2 = Hub(DemoLLM(delay=0), store)
    assert hub2.open_conversation(hub.current.id) is None
    restored = [m for m in hub2.current.agent.messages if m["role"] == "user"][0]
    assert restored["content"][1]["image_url"]["url"] == PNG_1PX


def test_image_only_message_and_invalid_images(store, ws_dir):
    client, hub = make_client(store, ws_dir)
    with client.websocket_connect("/ws") as ws:
        drain_snapshot(ws)
        ws.send_json({"type": "user_message", "text": "", "images": ["data:text/html;base64,PGI+"]})
        assert "图片无法使用" in ws.receive_json()["text"]
        ws.send_json({"type": "user_message", "text": "", "images": [PNG_1PX] * 5})
        assert "最多" in ws.receive_json()["text"]
        ws.send_json({"type": "user_message", "text": "", "images": [PNG_1PX]})
        collect_until_done(ws)
    assert hub.current.title == "图片"
    first_user = [m for m in hub.current.agent.messages if m["role"] == "user"][0]
    assert first_user["content"][0]["text"] == "请看图片。"   # 只发图片时给模型的默认文字
    assert client.get("/api/image/../../secret.png").status_code == 404


def test_info_and_state_carry_version_and_demo_flag(store, ws_dir):
    import os
    from coder import __version__
    client, hub = make_client(store, ws_dir)
    info = client.get("/api/info").json()
    assert info == {"app": "coder", "version": __version__, "pid": os.getpid(), "demo": False}
    hub.demo = True
    with client.websocket_connect("/ws") as ws:
        state = [e for e in drain_snapshot(ws) if e["type"] == "state"][0]
    assert state["version"] == __version__ and state["demo"] is True


def test_port_in_use_detection():
    import socket
    from coder.web.__main__ import port_in_use
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        port = s.getsockname()[1]
        assert port_in_use(port)
    assert not port_in_use(port)


def test_team_mode_toggle_persist_and_tagged_cards(store, ws_dir):
    from coder.team import Team
    client, hub = make_client(store, ws_dir)
    with client.websocket_connect("/ws") as ws:
        drain_snapshot(ws)
        ws.send_json({"type": "set_team", "value": True})
        while (ev := ws.receive_json())["type"] != "state":
            pass
        assert ev["team"] is True and isinstance(hub.current.agent, Team)
        run_task(ws)  # 演示模型不会拆分任务：主 agent 自己完成，和单 agent 一样
        # 子 agent 的工具调用：卡片带上任务名，并行时各自配对结果
        ui = hub.current.ui
        ui.sub_tool_call("core", "read_file", {"path": "a.py"})
        ui.sub_tool_call("cli", "read_file", {"path": "b.py"})
        ui.sub_tool_result("core", "错误：文件不存在")
        events = [ws.receive_json() for _ in range(3)]
    calls = {e["agent"]: e["id"] for e in events if e["type"] == "tool_call"}
    result = next(e for e in events if e["type"] == "tool_result")
    assert set(calls) == {"core", "cli"} and result["id"] == calls["core"] and result["is_error"]
    assert "你好" in (ws_dir / "hello.py").read_text(encoding="utf-8")

    hub2 = Hub(DemoLLM(delay=0), store)  # 重启后仍是团队模式，主 agent 的历史和用量恢复
    hub2.open_latest()
    assert isinstance(hub2.current.agent, Team) and hub2.current.agent.usage["prompt"] > 0
    assert len(hub2.current.agent.messages) > 5
    hub2.current.set_team(False)  # 切回单 agent，历史保留
    assert not isinstance(hub2.current.agent, Team) and len(hub2.current.agent.messages) > 5


def test_settings_api_saves_env_and_switches_model(store, ws_dir, tmp_path, monkeypatch):
    """设置面板：密钥不发给浏览器；保存后写进 .env、立即换成新的模型客户端；没配置时不能发消息。"""
    from coder import config
    env = tmp_path / "settings.env"
    monkeypatch.setattr(config, "settings_file", lambda: env)
    import coder.web.server as server_mod
    monkeypatch.setattr(server_mod, "settings_file", lambda: env)
    monkeypatch.setattr(server_mod, "save_settings", lambda values: config.save_settings(values, env))
    for k in ("CODER_API_KEY", "DEEPSEEK_API_KEY", "CODER_PROVIDER", "CODER_BASE_URL", "CODER_MODEL"):
        monkeypatch.setenv(k, "")  # 测试结束后恢复
    hub = Hub(None, store)  # 没有密钥启动
    assert hub.open_workspace(str(ws_dir)) is None
    client = TestClient(create_app(hub))
    with client.websocket_connect("/ws") as ws:
        state = [e for e in drain_snapshot(ws) if e["type"] == "state"][-1]
        assert state["configured"] is False
        ws.send_json({"type": "user_message", "text": "你好"})
        assert "还没有配置模型" in ws.receive_json()["text"]

    s = client.get("/api/settings").json()
    assert {p["id"] for p in s["providers"]} == {"deepseek", "custom"} and not s["current"]["has_key"]
    proxy = {"provider": "custom", "base_url": "http://127.0.0.1:8000/v1", "model": "my-model"}
    assert client.post("/api/settings", json=proxy).status_code == 400  # 没有密钥
    r = client.post("/api/settings", json={**proxy, "api_key": "sk-secret"})
    assert r.status_code == 200
    assert "CODER_API_KEY=sk-secret" in env.read_text(encoding="utf-8")
    assert hub.llm.model == "my-model" and hub.llm.provider == "custom"
    assert hub.current.agent.llm is hub.llm  # 当前对话也换成了新的客户端
    s = client.get("/api/settings").json()
    assert s["current"] == {"provider": "custom", "base_url": "http://127.0.0.1:8000/v1", "model": "my-model", "has_key": True}
    assert "sk-secret" not in str(s)  # 密钥不会发给浏览器
    # 换回 DeepSeek 官方、留空密钥：沿用已保存的
    assert client.post("/api/settings", json={"provider": "deepseek", "model": "deepseek-flash"}).status_code == 200
    assert hub.llm.provider == "deepseek" and "CODER_API_KEY=sk-secret" in env.read_text(encoding="utf-8")
    assert client.post("/api/settings", json={"provider": "custom", "model": "m"}).status_code == 400  # 自定义要填地址


def test_undo_last_turn_from_web(store, ws_dir):
    client, hub = make_client(store, ws_dir)
    with client.websocket_connect("/ws") as ws:
        drain_snapshot(ws)
        run_task(ws)
        assert (ws_dir / "hello.py").exists()
        assert hub.state()["undo"] == "写个 hello"
        ws.send_json({"type": "undo"})
        notice = ws.receive_json()
        assert notice["type"] == "notice" and "已撤销" in notice["text"]
    assert not (ws_dir / "hello.py").exists() and hub.state()["undo"] == ""


def test_command_prefix_rules_listed_and_removed(store, ws_dir):
    client, hub = make_client(store, ws_dir)
    hub.current.permissions.allow_prefix("python -m pytest")
    assert client.get("/api/settings").json()["rules"] == ["python -m pytest"]
    assert (ws_dir / ".coder" / "permissions.json").is_file()
    assert client.post("/api/rules/remove", json={"prefix": "python -m pytest"}).json()["rules"] == []


def test_sandbox_toggle_checks_docker_and_rebuilds_agent(store, ws_dir, monkeypatch):
    import coder.web.server as server
    saved = {}
    monkeypatch.setattr(server, "save_settings", lambda values: saved.update(values))  # 不写真实的 .env
    client, hub = make_client(store, ws_dir)
    monkeypatch.setattr(server, "docker_status", lambda: (False, "Docker 没有在运行"))
    r = client.post("/api/sandbox", json={"enabled": True})
    assert r.status_code == 400 and "没有在运行" in r.json()["detail"] and hub.current.sandbox is None
    monkeypatch.setattr(server, "docker_status", lambda: (True, "ok"))
    assert client.post("/api/sandbox", json={"enabled": True}).status_code == 200
    c = hub.current
    assert c.sandbox and c.agent.sandbox is c.sandbox and "network" in c.agent.tools["run_command"].parameters["properties"]
    assert hub.state()["sandbox"] is True and saved == {"CODER_SANDBOX": "1"}
    assert client.post("/api/sandbox", json={"enabled": False}).status_code == 200
    assert hub.current.sandbox is None and saved == {"CODER_SANDBOX": "0"}


def test_team_state_survives_restart(store, ws_dir):
    """团队模式的对话保存黑板和子 agent；重新打开时恢复，用量不重复计算。"""
    client, hub = make_client(store, ws_dir)
    c = hub.current
    c.set_team(True)
    team = c.agent
    team.plan([{"id": "core", "role": "backend", "description": "实现", "files": ["core.py"]}], [])
    sub = team._make_agent("core", ["core.py"], 5, c.ui)
    sub.messages.append({"role": "user", "content": "任务说明"})
    sub.usage = {"prompt": 30, "completion": 3, "cached": 0}
    team.subagents["core"] = sub
    team.lead.usage = {"prompt": 70, "completion": 7, "cached": 0}
    team.board.set_status("core", "running")
    c.save()
    data = store.load(c.id)
    assert data["team_state"]["board"]["tasks"]["core"]["status"] == "running"

    from coder.web.session import Conversation
    again = Conversation(hub, ws_dir, data)
    assert again.team and again.agent.board.tasks["core"]["status"] == "interrupted"
    assert again.agent.subagents["core"].messages[-1]["content"] == "任务说明"
    assert again.agent.usage == {"prompt": 100, "completion": 10, "cached": 0}  # 合计不变
    assert any("服务重启前" in e.get("text", "") for e in again.events)


def test_sandbox_previews_in_state(store, ws_dir, monkeypatch):
    import coder.web.server as server
    monkeypatch.setattr(server, "save_settings", lambda values: None)
    monkeypatch.setattr(server, "docker_status", lambda: (True, "ok"))
    client, hub = make_client(store, ws_dir)
    client.post("/api/sandbox", json={"enabled": True})
    fw = hub.current.sandbox.forwarder
    fw.forwards[5173] = {"host_port": 5173, "server": type("S", (), {"close": lambda self: None})()}
    assert hub.state()["previews"] == [{"port": 5173, "url": "http://127.0.0.1:5173"}]
    fw.stop(5173)
    assert hub.state()["previews"] == []


def test_message_while_running_becomes_steering(store, ws_dir):
    """运行中发消息不再被拒绝：作为插话显示出来，在当前这一步结束后交给 agent。"""
    client, hub = make_client(store, ws_dir, auto=False)
    with client.websocket_connect("/ws") as ws:
        drain_snapshot(ws)
        ws.send_json({"type": "user_message", "text": "写个 hello"})
        events, steered = [], False
        while True:
            ev = ws.receive_json()
            events.append(ev)
            if ev["type"] == "permission_request":
                if not steered:  # 等确认时任务一定在运行：这时补充一句
                    steered = True
                    ws.send_json({"type": "user_message", "text": "顺便加上注释"})
                    while (e := ws.receive_json())["type"] != "user":
                        events.append(e)
                    events.append(e)
                ws.send_json({"type": "permission_response", "id": ev["id"], "choice": "y", "feedback": ""})
            if ev["type"] == "done":
                break
    interject = [e for e in events if e["type"] == "user" and e.get("interject")]
    assert interject and interject[0]["text"] == "顺便加上注释"
    msgs = hub.current.agent.messages
    assert any(m["role"] == "user" and "顺便加上注释" in str(m["content"]) and "补充" in str(m["content"]) for m in msgs)


def test_open_a_scratch_conversation_from_a_project(store, ws_dir):
    """已经打开了项目对话，也能从工作区选择框开一个临时对话。"""
    client, hub = make_client(store, ws_dir)
    project = hub.current
    hub.handle({"type": "new_conversation", "scratch": True})
    assert hub.current is not project and hub.current.scratch
    hub.handle({"type": "new_conversation"})          # 临时对话里点"新对话"：还是临时对话
    assert hub.current.scratch and hub.current.workspace.root != ws_dir.resolve()


def test_sandbox_works_on_copy_until_applied(store, ws_dir, monkeypatch):
    """沙箱模式：agent 改的是副本；应用 / 放弃；有待应用的改动时不能关沙箱；删对话连副本一起删。"""
    import coder.web.server as server
    monkeypatch.setattr(server, "save_settings", lambda values: None)
    monkeypatch.setattr(server, "docker_status", lambda: (True, "ok"))
    (ws_dir / "a.py").write_text("a = 1\n", encoding="utf-8")
    client, hub = make_client(store, ws_dir)
    client.post("/api/sandbox", json={"enabled": True})
    c = hub.current
    copy = c.shadow.copy
    assert c.workspace.root == copy and c.real_root == ws_dir.resolve() and (copy / "a.py").is_file()
    assert hub.state()["conversation"]["workspace"] == str(ws_dir.resolve())

    (copy / "a.py").write_text("a = 2\n", encoding="utf-8")   # 相当于 agent 在副本里改了
    (copy / "b.py").write_text("b = 1\n", encoding="utf-8")
    assert hub.state()["sandbox_changes"]["modified"] == ["a.py"]
    assert (ws_dir / "a.py").read_text(encoding="utf-8") == "a = 1\n"
    r = client.post("/api/sandbox", json={"enabled": False})
    assert r.status_code == 409 and "没应用" in r.json()["detail"] and c.shadow

    hub.handle({"type": "sandbox_apply"})
    assert (ws_dir / "a.py").read_text(encoding="utf-8") == "a = 2\n" and (ws_dir / "b.py").is_file()
    assert hub.state()["sandbox_changes"] is None

    (copy / "a.py").write_text("a = 3\n", encoding="utf-8")
    hub.handle({"type": "sandbox_discard"})
    assert (copy / "a.py").read_text(encoding="utf-8") == "a = 2\n"

    (ws_dir / "c.py").write_text("c = 1\n", encoding="utf-8")   # 用户自己在项目里加的文件，下一轮前同步进副本
    monkeypatch.setattr(c.agent, "run", lambda text, images=None: None)  # 不真的跑（演示模型会执行命令、启动容器）
    c._run("继续", [])
    assert (copy / "c.py").is_file()
    conv_id = c.id
    hub.handle({"type": "delete_conversation", "id": conv_id})
    assert not copy.exists()
