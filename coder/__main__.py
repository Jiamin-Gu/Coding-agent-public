"""命令行入口：python -m coder [工作区路径] [--auto] [-p 任务]"""
import argparse
import os
import sys
from pathlib import Path

from openai import APIError

from . import __version__, use_utf8_output
from .agent import Agent
from .checkpoints import describe
from .config import Config
from .llm import LLM
from .permissions import PermissionManager, rules_file
from .mcp import MCPManager
from .sandbox import DockerSandbox, docker_status
from .shadow import Shadow, describe as describe_changes
from .team import Team
from .tools import ProcessManager, build_tools
from .ui import BOLD, RESET, ConsoleUI
from .workspace import Workspace

HELP = """命令：
  /help     显示帮助
  /reset    清空对话历史
  /auto     切换自动模式（写文件和执行命令不再询问）
  /rules    查看总是允许的命令前缀；/rules rm 序号 删除一条
  /usage    查看 token 用量
  /undo     撤销上一轮 agent 对文件的修改（命令产生的效果无法撤销）
  /ps       查看 agent 启动的后台进程；/ps stop 编号 停止一个
  /mcp      查看 MCP 服务器和它们提供的工具
  /compact  立即把早期对话压缩成摘要（上下文太长时也会自动压缩）
  /exit     退出
执行中按 Ctrl+C 可中断当前任务。"""


def main() -> None:
    parser = argparse.ArgumentParser(description="从零实现的 coding agent（命令行版）")
    parser.add_argument("workspace", nargs="?", default=".", help="agent 能访问的项目目录，默认当前目录")
    parser.add_argument("-p", "--prompt", help="一次性执行这个任务后退出（不进入交互模式）")
    parser.add_argument("--auto", action="store_true", help="自动模式：不再逐个确认写文件和执行命令")
    parser.add_argument("--model", help="覆盖默认模型")
    parser.add_argument("--team", nargs="?", const="auto", choices=["auto", "always"],
                        help="团队模式：主 agent 可以把大任务拆分给子 agent 并行完成（auto 由它判断，always 必须拆分）")
    parser.add_argument("--sandbox", action="store_true",
                        help="沙箱模式：agent 在项目副本上工作，命令在 Docker 容器里执行（默认断网）；"
                             "每个任务结束后由你决定是否把改动应用到项目。也可以在 .env 里设 CODER_SANDBOX=1")
    parser.add_argument("--version", action="version", version=f"coder {__version__}")
    args = parser.parse_args()
    use_utf8_output()

    cfg = Config.from_env()
    if args.model:
        cfg.model = args.model
    if not cfg.api_key:
        sys.exit("未找到 CODER_API_KEY。请复制 .env.example 为 .env 并填入你的 key。")

    root = Path(args.workspace)
    if not root.is_dir():
        sys.exit(f"目录不存在：{root}")

    if os.name == "nt":
        os.system("")  # 让旧版 Windows 控制台支持 ANSI 颜色
    ui = ConsoleUI()
    real_root = root.resolve()
    sandbox = shadow = None
    if args.sandbox or cfg.sandbox:
        ok, why = docker_status()
        if not ok:
            sys.exit(f"无法使用沙箱模式：{why}")
        # agent 在项目副本上工作（见 shadow.py），退出时删掉副本
        home = Path(os.getenv("CODER_HOME") or Path.home() / ".coder")
        shadow = Shadow(real_root, home / "sandbox-copies" / f"cli-{os.getpid()}")
        print("正在复制项目到沙箱副本 ……", flush=True)
        shadow.ensure()
    workspace = Workspace(shadow.copy if shadow else real_root)
    if shadow:
        sandbox = DockerSandbox(workspace.root)
    try:
        _run(args, cfg, ui, workspace, real_root, sandbox, shadow)
    finally:
        if sandbox:
            sandbox.stop()  # 先停容器（它挂载着副本），再删副本
        if shadow:
            shadow.remove()


def _review_changes(shadow: Shadow, ui: ConsoleUI, auto_apply: bool = False) -> None:
    """沙箱模式：任务结束后列出副本里的改动，问用户应用到项目还是放弃（一次性模式直接应用）。"""
    ch = shadow.changes()
    if not any(ch.values()):
        return
    ui.info(f"沙箱副本里的改动：{describe_changes(ch, limit=30)}")
    while not auto_apply:
        try:
            choice = input("应用到项目？[a] 应用 / [d] 放弃 / [k] 先保留，下个任务后再决定：").strip().lower()
        except (EOFError, KeyboardInterrupt):
            choice = "k"
        if choice == "d":
            ui.info(f"已放弃（{len(shadow.discard())} 个文件恢复成项目里的样子）")
            return
        if choice == "k":
            return
        if choice == "a":
            break
    result = shadow.apply()
    ui.info(f"已把 {len(result['applied'])} 个文件的改动应用到项目")
    if result["conflicts"]:
        ui.warn(f"这些文件你在项目里也改过，没有覆盖：{'、'.join(result['conflicts'])}。"
                f"副本在 {shadow.copy}，可以对照着手动合并")


def _run(args, cfg: Config, ui: ConsoleUI, workspace: Workspace, real_root: Path,
         sandbox: DockerSandbox | None, shadow: Shadow | None) -> None:
    processes = ProcessManager(sandbox)
    mcp = MCPManager(real_root)
    if mcp.config:
        print(f"启动 MCP 服务器：{', '.join(mcp.config)} ……", flush=True)
        mcp.start()
    permissions = PermissionManager(ask=ui.ask_permission, auto=args.auto, rules_path=rules_file(real_root))
    if args.team:
        agent = Team(lambda: LLM(cfg), workspace.root, permissions, ui, max_steps=cfg.max_steps,
                     context_limit=cfg.context_limit, delegate=args.team, processes=processes, sandbox=sandbox)
        agent.attach_mcp(mcp)
    else:
        agent = Agent(LLM(cfg), build_tools(workspace, processes, sandbox, mcp), workspace, permissions, ui,
                      max_steps=cfg.max_steps, max_tool_output=cfg.max_tool_output,
                      context_limit=cfg.context_limit, sandbox=sandbox)

    if args.prompt:  # 一次性模式：适合脚本调用。沙箱模式下改动直接应用到项目（没人可问）
        try:
            agent.run(args.prompt)
        except KeyboardInterrupt:
            sys.exit(130)
        except APIError as e:
            sys.exit(f"API 调用失败：{e}")
        if shadow:
            _review_changes(shadow, ui, auto_apply=True)
        return

    print(f"{BOLD}coder v{__version__}{RESET} · 模型 {cfg.model} · 工作区 {real_root}")
    print(f"权限模式：{'自动' if args.auto else '逐个确认'}"
          f"{' · 沙箱（项目副本 + Docker，默认断网）' if sandbox else ''}"
          f"{' · 团队模式（' + args.team + '）' if args.team else ''} · 输入 /help 查看命令")

    while True:
        try:
            text = input(f"\n{BOLD}> {RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            text = "/exit"
        if not text:
            continue
        if text == "/exit":
            if shadow and shadow.pending():  # 退出会删掉副本：还没处理的改动最后问一次
                _review_changes(shadow, ui)
                if shadow.pending():
                    ui.warn("副本里还有没应用的改动，退出后会被删除。再输入一次 /exit 确认退出")
                    try:
                        if input(f"\n{BOLD}> {RESET}").strip() != "/exit":
                            continue
                    except (EOFError, KeyboardInterrupt):
                        pass
            break
        if text == "/help":
            print(HELP)
            continue
        if text == "/reset":
            agent.reset()
            if processes.stop_all():
                ui.info("已停止之前启动的后台进程")
            ui.info("对话历史已清空")
            continue
        if text == "/auto":
            permissions.auto = not permissions.auto
            ui.info(f"自动模式：{'开' if permissions.auto else '关'}")
            continue
        if text == "/rules" or text.startswith("/rules "):
            parts = text.split()
            rules = permissions.allowed_prefixes
            if len(parts) == 3 and parts[1] == "rm" and parts[2].isdigit() and 1 <= int(parts[2]) <= len(rules):
                removed = rules[int(parts[2]) - 1]
                permissions.remove_prefix(removed)
                ui.info(f"已删除：{removed}")
            elif rules:
                ui.info("总是允许的命令前缀（保存在 .coder/permissions.json）：\n"
                        + "\n".join(f"  {i}. {r}" for i, r in enumerate(rules, 1)))
            else:
                ui.info("还没有命令前缀规则。确认命令时选 [p] 即可添加")
            continue
        if text == "/mcp":
            ui.info(mcp.describe())
            continue
        if text == "/ps" or text.startswith("/ps "):
            parts = text.split()
            if len(parts) == 3 and parts[1] == "stop" and parts[2] in processes.procs:
                processes.stop(parts[2])
                ui.info(f"已停止 {parts[2]}")
            elif processes.procs:
                ui.info(build_tools(workspace, processes)["list_processes"].run())
            else:
                ui.info("没有后台进程")
            continue
        if text in ("/undo", "/undo!"):
            result = agent.undo(force=text == "/undo!")
            ui.info(describe(result).replace("请用强制撤销", "请输入 /undo!"))
            continue
        if text == "/usage":
            u = agent.usage
            ui.info(f"输入 {u['prompt']} tokens（其中缓存命中 {u['cached']}）· 输出 {u['completion']} tokens"
                    f" · 当前上下文约 {agent.context_tokens():,} tokens")
            continue
        if text == "/compact":
            try:
                ui.info("已压缩" if agent.compact() else "对话太短，不需要压缩")
            except APIError as e:
                ui.error(f"API 调用失败：{e}")
            continue
        if shadow:  # 没有待应用的改动时，把用户在项目里的修改同步进副本
            synced = shadow.refresh()
            if synced:
                ui.info(f"已把你在项目里改动的 {len(synced)} 个文件同步进沙箱副本")
        try:
            agent.run(text)
        except KeyboardInterrupt:
            agent.interrupt()
            ui.warn("\n已中断")
        except APIError as e:
            ui.error(f"API 调用失败：{e}")
        if shadow:
            _review_changes(shadow, ui)


if __name__ == "__main__":
    main()
