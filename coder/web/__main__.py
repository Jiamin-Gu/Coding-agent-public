"""Web 界面入口：python -m coder.web [工作区路径] [--auto] [--demo] [--port 8765]"""
import argparse
import json
import os
import socket
import sys
import tempfile
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

import uvicorn

from .. import __version__, use_utf8_output
from ..config import Config
from ..store import Store
from .guard import allowed_hosts, load_token
from .server import create_app
from .session import Hub


TOKEN_NOTE = '  链接里的 token 是访问令牌：防止你浏览的其他网站在后台操作{what}。它保存在本机、不会上传，不要发给别人。\n  这个浏览器打开过一次之后，直接访问 {url} 也可以。'


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return False
        except OSError:
            return True


def fetch_info(url: str) -> dict | None:
    """读取 url 上 coder 服务的信息；不是 coder（或没有响应）时返回 None。"""
    # 绕过系统代理：很多人设置了 HTTP_PROXY，访问 127.0.0.1 也会被转发到代理而失败
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url + "/api/info", timeout=1) as r:
            info = json.load(r)
            return info if info.get("app") == "coder" else None
    except (OSError, ValueError):
        return None


def open_browser_when_ready(url: str, link: str) -> None:
    """等确认是本进程的服务在响应，才打开浏览器（用带令牌的链接），避免连到别的（比如旧的）服务上。"""
    for _ in range(50):
        info = fetch_info(url)
        if info and info.get("pid") == os.getpid():
            webbrowser.open(link)
            return
        time.sleep(0.2)


def main() -> None:
    parser = argparse.ArgumentParser(description="coder 的浏览器界面")
    parser.add_argument("workspace", nargs="?",
                        help="直接在这个目录开一个新对话；不填则打开上次的对话，或在界面里选择工作区")
    parser.add_argument("--auto", action="store_true", help="自动模式：写文件和执行命令不再确认")
    parser.add_argument("--demo", action="store_true", help="演示模式：用脚本化的假模型，不需要 API key")
    parser.add_argument("--model", help="覆盖默认模型")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args()
    use_utf8_output()

    # 先检查端口：被占用时 uvicorn 只会打印一行报错，很容易被忽略
    url = f"http://127.0.0.1:{args.port}"
    # 访问令牌：防止用户浏览的其他网站操作 agent（见 guard.py）。保存在 ~/.coder，重启不变，演示模式也用同一个
    token = load_token(Path(os.getenv("CODER_HOME") or Path.home() / ".coder"))
    link = f"{url}/?token={token}"
    if port_in_use(args.port):
        info = fetch_info(url)
        if info and info.get("version") == __version__ and info.get("demo") == args.demo:
            # 同版本、同模式的 coder 已经在运行（比如又双击了一次 start.bat）：直接打开它
            print(f"coder 已经在运行：{url}" + ("" if args.no_browser else "，已为你打开浏览器"))
            if args.workspace:
                print(f"要切换到 {args.workspace}，请在页面顶部点 📁 选择")
            if not args.no_browser:
                webbrowser.open(link)
            return
        if info:
            running = f"coder v{info.get('version', '?')}" + ("（演示模式）" if info.get("demo") else "")
            reason = f"端口 {args.port} 上已经运行着 {running}，和这次要启动的版本或模式不同。"
        else:
            reason = f"端口 {args.port} 已被占用，很可能是之前启动的 coder 还在运行。"
        sys.exit(
            f"\n启动失败：{reason}\n"
            f"  · 找到运行它的终端窗口，按 Ctrl+C 关闭，再重新启动；\n"
            f"  · 或者换一个端口启动：python -m coder.web --port {args.port + 1}\n"
        )

    cfg = Config.from_env()
    if args.model:
        cfg.model = args.model

    if args.demo:
        from ..demo import DemoLLM
        llm = DemoLLM()
        # 演示数据和真实对话分开存，避免混在一起
        store = Store(tempfile.mkdtemp(prefix="coder-demo-home-"))
        workspace = args.workspace or tempfile.mkdtemp(prefix="coder-demo-")
    else:
        from ..llm import LLM
        llm = LLM(cfg) if cfg.api_key else None  # 没有密钥也能启动：在网页的设置里填写
        store = Store()
        workspace = args.workspace

    hub = Hub(llm, store, auto=args.auto, max_steps=cfg.max_steps,
              max_tool_output=cfg.max_tool_output, demo=args.demo,
              context_limit=cfg.context_limit, sandbox=cfg.sandbox and not args.demo)
    if workspace:
        err = hub.open_workspace(workspace)
        if err:
            sys.exit(err)
    else:
        hub.open_latest()

    mode = ("演示模式（假模型）" if args.demo else f"模型：{llm.model}" if llm
            else "还没有配置模型：网页打开后会弹出「模型设置」，选择服务商、填写 API Key 即可")
    print(f"coder v{__version__} 已启动，浏览器会自动打开：{link}\n  {mode}\n  对话保存在：{store.home}")
    print(TOKEN_NOTE.format(what="你的 agent", url=url))
    print("关闭服务：关掉这个窗口，或者按 Ctrl+C")
    if not args.no_browser:
        threading.Thread(target=open_browser_when_ready, args=(url, link), daemon=True).start()
    # 只监听本机：agent 能改文件和执行命令，不能暴露到局域网
    # ws_max_size：消息里可能带几张截图（base64），默认 16 MB 不够
    uvicorn.run(create_app(hub, token=token, hosts=allowed_hosts(args.port)), host="127.0.0.1", port=args.port,
                log_level="warning",
                ws_max_size=48 * 1024 * 1024)


if __name__ == "__main__":
    main()
