"""HTTP + WebSocket 服务。页面是纯静态文件，所有交互走 /ws。"""
import asyncio
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import __version__, providers
from ..config import Config, save_settings, settings_file
from ..sandbox import docker_status
from ..tools.fs import MAX_FILE_BYTES, is_binary, read_text
from ..workspace import IGNORED_DIRS, WorkspaceError
from .guard import Guard
from .session import Hub

STATIC = Path(__file__).parent / "static"
MAX_TREE_FILES = 2000


class SettingsIn(BaseModel):
    provider: str
    base_url: str = ""
    model: str
    api_key: str = ""  # 留空表示沿用已保存的密钥


class RuleIn(BaseModel):
    prefix: str


class SandboxIn(BaseModel):
    enabled: bool


def pick_folder() -> str:
    """弹出系统的文件夹选择框。服务只在本机运行，所以对话框会出现在用户自己的屏幕上。"""
    import tkinter
    from tkinter import filedialog

    root = tkinter.Tk()
    root.withdraw()
    root.attributes("-topmost", True)  # 否则对话框可能藏在浏览器后面
    try:
        return filedialog.askdirectory(title="选择工作区文件夹", mustexist=True) or ""
    finally:
        root.destroy()


def create_app(hub: Hub, token: str | None = None, hosts: set[str] | None = None) -> FastAPI:
    """token：访问令牌（见 guard.py），None 表示不检查（只在测试里这样用）。
    hosts：允许的 Host，正式运行时是 127.0.0.1 / localhost 加端口；默认只有测试客户端用的 testserver。"""
    app = FastAPI(title="coder")
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    app.add_middleware(Guard, token=token, hosts=hosts or {"testserver"})

    @app.middleware("http")
    async def no_cache(request, call_next):
        # 前端文件更新后浏览器要立刻拿到新版本，而不是用缓存
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-cache"
        return response

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/info")
    def info():
        # 启动时用 pid 确认浏览器连的是本进程，而不是之前没关的旧服务
        return {"app": "coder", "version": __version__, "pid": os.getpid(), "demo": hub.demo}

    @app.get("/api/files")
    def files():
        """当前工作区的文件列表（扁平路径），前端自己拼成树。"""
        if not hub.current:
            return {"files": [], "truncated": False}
        root = hub.current.workspace.root
        out: list[str] = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if d not in IGNORED_DIRS)
            for name in sorted(filenames):
                out.append((Path(dirpath) / name).relative_to(root).as_posix())
                if len(out) >= MAX_TREE_FILES:
                    return {"files": out, "truncated": True}
        return {"files": out, "truncated": False}

    @app.get("/api/file")
    def file(path: str):
        if not hub.current:
            raise HTTPException(404, "没有打开的工作区")
        try:
            p = hub.current.workspace.resolve(path)
        except WorkspaceError as e:
            raise HTTPException(403, str(e))
        if not p.is_file():
            raise HTTPException(404, "文件不存在")
        if p.stat().st_size > MAX_FILE_BYTES or is_binary(p):
            return {"path": path, "content": None, "note": "二进制或过大的文件，不显示内容"}
        return {"path": path, "content": read_text(p)[0]}

    @app.get("/api/image/{image_id}")
    def image(image_id: str):
        path = hub.store.image_path(image_id)
        if not path:
            raise HTTPException(404, "图片不存在")
        return FileResponse(path)

    @app.get("/api/settings")
    def get_settings():
        """当前的模型设置和可选的服务商。密钥只告诉前端有没有设置，不发送内容。"""
        cfg = Config.from_env()
        return {"providers": providers.public_list(), "file": str(settings_file()), "demo": hub.demo,
                "current": {"provider": cfg.provider, "base_url": cfg.base_url, "model": cfg.model,
                            "has_key": bool(cfg.api_key)},
                "rules": hub.current.permissions.allowed_prefixes if hub.current else [],
                "sandbox": {"enabled": hub.sandbox, "status": docker_status()[1]},
                "mcp": hub.current.mcp.status() if hub.current else [],
                "workspace": str(hub.current.workspace.root) if hub.current else ""}

    @app.post("/api/sandbox")
    def set_sandbox(body: SandboxIn):
        """开关沙箱模式：开启前检查 Docker 和镜像，保存到 .env，下次启动仍然有效。"""
        if body.enabled:
            if hub.demo:
                raise HTTPException(400, "演示模式不执行真实命令，不需要沙箱")
            ok, why = docker_status()
            if not ok:
                raise HTTPException(400, why)
        err = hub.set_sandbox(body.enabled)
        if err:
            raise HTTPException(409, err)
        save_settings({"CODER_SANDBOX": "1" if body.enabled else "0"})
        return {"enabled": body.enabled}

    @app.post("/api/rules/remove")
    def remove_rule(body: RuleIn):
        """删除一条"总是允许的命令前缀"规则（当前对话的工作区）。"""
        if not hub.current:
            raise HTTPException(400, "还没有打开工作区")
        hub.current.permissions.remove_prefix(body.prefix)
        return {"rules": hub.current.permissions.allowed_prefixes}

    @app.post("/api/settings")
    def put_settings(body: SettingsIn):
        if body.provider not in providers.PROVIDERS:
            raise HTTPException(400, "未知的服务商")
        base_url = body.base_url.strip() or providers.get(body.provider).base_url
        model, key = body.model.strip(), body.api_key.strip()
        if not base_url.startswith(("http://", "https://")):
            raise HTTPException(400, "请填写接口地址（以 http:// 或 https:// 开头）")
        if not model:
            raise HTTPException(400, "请填写模型名")
        if not key and not Config.from_env().api_key:
            raise HTTPException(400, "请填写 API Key")
        if hub.busy:
            raise HTTPException(409, "任务运行中，请先停止再修改设置")
        values = {"CODER_PROVIDER": body.provider, "CODER_BASE_URL": base_url, "CODER_MODEL": model}
        if key:
            values["CODER_API_KEY"] = key
        path = save_settings(values)
        if hub.demo:
            return {"ok": True, "file": str(path), "note": "已保存。演示模式不使用真实模型，用正常模式启动后生效"}
        from ..llm import LLM
        err = hub.set_llm(LLM(Config.from_env()))
        if err:
            raise HTTPException(409, err)
        return {"ok": True, "file": str(path)}

    @app.post("/api/pick-folder")
    def pick():
        # 普通 def 会在线程池里运行，对话框阻塞时不影响其他请求
        try:
            return {"path": pick_folder()}
        except Exception as e:  # 没有 tkinter 或没有图形界面
            return {"path": "", "error": f"无法打开文件夹选择框（{e}），请手动输入路径"}

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        await ws.accept()
        q: asyncio.Queue = asyncio.Queue()
        hub.attach(q)

        async def pump():
            while True:
                await ws.send_json(await q.get())

        sender = asyncio.create_task(pump())
        try:
            while True:
                hub.handle(await ws.receive_json())
        except WebSocketDisconnect:
            pass
        finally:
            sender.cancel()
            hub.detach(q)

    return app
