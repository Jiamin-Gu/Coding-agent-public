"""终端输出。和 agent 逻辑分开，方便以后换成 Web 界面或在测试里替换掉。"""
import json

RESET, DIM, BOLD = "\033[0m", "\033[2m", "\033[1m"
RED, GREEN, YELLOW, CYAN = "\033[31m", "\033[32m", "\033[33m", "\033[36m"


def color_diff(text: str) -> str:
    out = []
    for line in text.split("\n"):
        if line.startswith("+") and not line.startswith("+++"):
            out.append(GREEN + line + RESET)
        elif line.startswith("-") and not line.startswith("---"):
            out.append(RED + line + RESET)
        else:
            out.append(line)
    return "\n".join(out)


class ConsoleUI:
    def __init__(self):
        self._streaming: str | None = None  # 正在流式输出的类型

    def delta(self, kind: str, text: str) -> None:
        if self._streaming != kind:
            print("\n" + (f"{DIM}[思考] " if kind == "reasoning" else RESET), end="")
            self._streaming = kind
        print(text, end="", flush=True)

    def assistant(self, text: str, reasoning: str | None = None) -> None:
        if self._streaming:  # 已经流式打印过了，只需收尾
            print(RESET)
            self._streaming = None
        elif text:
            print(f"\n{text}")

    def tool_call(self, name: str, args: dict) -> None:
        # 只展示简短参数，长内容（如文件全文）省略
        brief = {k: (v if not isinstance(v, str) or len(v) < 80 else v[:77] + "...")
                 for k, v in args.items()}
        print(f"\n{CYAN}● {name}{RESET} {DIM}{json.dumps(brief, ensure_ascii=False)}{RESET}")

    def sub_tool_call(self, who: str, name: str, args: dict) -> None:
        """团队模式：子 agent 的工具调用，前面标上任务名。"""
        brief = {k: (v if not isinstance(v, str) or len(v) < 60 else v[:57] + "...")
                 for k, v in args.items()}
        print(f"{YELLOW}[{who}]{RESET} {CYAN}● {name}{RESET} {DIM}{json.dumps(brief, ensure_ascii=False)}{RESET}")

    def sub_tool_result(self, who: str, result: str) -> None:
        """并行时只显示子 agent 工具结果的第一行，避免刷屏。"""
        first = result.strip().split("\n")[0][:100]
        print(f"{DIM}  [{who}] {first}{RESET}")

    def tool_result(self, result: str) -> None:
        lines = result.split("\n")
        shown = "\n".join("  " + line for line in lines[:6])
        more = f"\n  ...（共 {len(lines)} 行）" if len(lines) > 6 else ""
        print(f"{DIM}{shown}{more}{RESET}")

    def info(self, text: str) -> None:
        print(f"{DIM}{text}{RESET}")

    def warn(self, text: str) -> None:
        print(f"{YELLOW}{text}{RESET}")

    def error(self, text: str) -> None:
        print(f"{RED}{text}{RESET}")

    def ask_permission(self, tool_name: str, preview: str, prefix: str | None = None,
                       network: bool = False) -> tuple[str, str]:
        print(f"\n{YELLOW}{BOLD}需要确认：{tool_name}{'（这个命令要联网）' if network else ''}{RESET}")
        print(color_diff(preview))
        options = "[y] 是 / [n] 否 / [a] 本次会话总是允许此工具"
        if network:
            options = "[y] 允许这一次联网 / [n] 否 / [a] 本次会话允许命令联网"
        elif prefix:
            options += f" / [p] 以后总是允许以「{prefix}」开头的命令"
        while True:
            try:
                choice = input(f"{YELLOW}允许执行？{options}：{RESET}").strip().lower()
            except EOFError:  # 一次性模式被脚本调用、没有终端可以输入：按拒绝处理，并告诉模型原因
                print()
                return "n", "当前是非交互模式，没有人可以确认这个操作"
            if choice in ("y", "a") or (choice == "p" and prefix):
                return choice, ""
            if choice == "n":
                feedback = input(f"{YELLOW}告诉 agent 原因或改进建议（可直接回车跳过）：{RESET}").strip()
                return "n", feedback
