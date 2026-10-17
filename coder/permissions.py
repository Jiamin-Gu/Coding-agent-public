"""权限管理：决定有副作用的工具调用是否放行。

三种放行方式：
- 自动模式：全部放行（危险命令仍会被工具自身拦截）
- 某个工具"本次会话总是允许"
- 命令前缀规则：例如"总是允许以 python -m pytest 开头的命令"。可以保存到项目的 .coder/permissions.json，
  下次打开这个项目仍然有效。带 &&、;、| 等连接符或重定向的命令不按规则放行（防止在允许的命令后面夹带别的命令）
"""
import json
import re
import shlex
from pathlib import Path
from typing import Callable

# 询问函数：(工具名, 预览内容, prefix=可以设为规则的命令前缀) -> (用户选择 y/n/a/p, 拒绝时的反馈)
AskFn = Callable[..., tuple[str, str]]
COMMAND_TOOLS = {"run_command", "start_process"}
# 这些程序的第二个词是子命令（git status、npm test），前缀取两个词
SUBCOMMAND_PROGRAMS = {"git", "npm", "pnpm", "yarn", "npx", "cargo", "go", "uv", "pip", "pip3", "poetry", "make",
                       "docker", "dotnet", "mvn", "gradle"}
# 解释器：后面跟的是要执行的代码，前缀要带上脚本名或模块名
INTERPRETERS = {"python", "python3", "py", "node", "deno", "bun", "ruby", "perl", "php",
                "bash", "sh", "powershell", "pwsh", "cmd"}
SHELL_OPERATORS = re.compile(r"&&|\|\||[;&|`<>]|\$\(")


def rules_file(root: str | Path) -> Path:
    return Path(root) / ".coder" / "permissions.json"


def command_prefix(command: str) -> str | None:
    """从命令里取出适合做规则的前缀：python -m pytest -q → "python -m pytest"；git status -s → "git status"。
    命令里有连接符、重定向时返回 None：这类命令不适合按前缀放行。"""
    command = command.strip()
    if not command or SHELL_OPERATORS.search(command):
        return None
    try:
        words = shlex.split(command, posix=False)
    except ValueError:
        return None
    if not words:
        return None
    first = words[0].lower()
    if first in INTERPRETERS:
        # 只允许 "python" 等于允许任意代码（python -c ...），所以至少要带上模块名或脚本名
        if len(words) >= 3 and words[1] == "-m":
            return " ".join(words[:3])
        if len(words) >= 2 and not words[1].startswith("-"):
            return " ".join(words[:2])
        return None
    if first in SUBCOMMAND_PROGRAMS and len(words) >= 2 and not words[1].startswith("-"):
        return " ".join(words[:2])
    return words[0]


def matches_prefix(command: str, prefix: str) -> bool:
    command = command.strip()
    if SHELL_OPERATORS.search(command):
        return False
    return command == prefix or command.startswith(prefix + " ")


class PermissionManager:
    def __init__(self, ask: AskFn, auto: bool = False, rules_path: str | Path | None = None):
        self.ask = ask
        self.auto = auto
        self.always_allowed: set[str] = set()   # 本次会话中用户选了"总是允许"的工具
        self.network_allowed = False            # 沙箱：本次会话中用户同意了命令联网
        self.rules_path = Path(rules_path) if rules_path else None
        self.allowed_prefixes: list[str] = self._load()  # 总是允许的命令前缀

    def check(self, tool_name: str, preview: str, command: str | None = None,
              network: bool = False) -> tuple[bool, str]:
        """返回 (是否放行, 用户反馈)。用户的拒绝理由会回传给模型，让它调整做法。"""
        if network and not self.network_allowed:
            # 沙箱里的命令要联网：自动模式、白名单都不算数，必须用户亲自同意（防止被诱导把代码或密钥发出去）
            choice, feedback = self.ask(tool_name, preview, network=True)
            if choice == "a":
                self.network_allowed = True
            return choice in ("y", "a"), feedback
        if self.auto or tool_name in self.always_allowed:
            return True, ""
        if command and any(matches_prefix(command, p) for p in self.allowed_prefixes):
            return True, ""
        prefix = command_prefix(command) if command and tool_name in COMMAND_TOOLS else None
        choice, feedback = self.ask(tool_name, preview, prefix=prefix) if prefix else self.ask(tool_name, preview)
        if choice == "a":
            self.always_allowed.add(tool_name)
            return True, ""
        if choice == "p" and prefix:
            self.allow_prefix(prefix)
            return True, ""
        return choice == "y", feedback

    def allow_prefix(self, prefix: str) -> None:
        if prefix not in self.allowed_prefixes:
            self.allowed_prefixes.append(prefix)
            self._save()

    def remove_prefix(self, prefix: str) -> None:
        if prefix in self.allowed_prefixes:
            self.allowed_prefixes.remove(prefix)
            self._save()

    def _load(self) -> list[str]:
        if not self.rules_path or not self.rules_path.is_file():
            return []
        try:
            data = json.loads(self.rules_path.read_text(encoding="utf-8"))
            return [p for p in data.get("command_prefixes", []) if isinstance(p, str) and p.strip()]
        except (OSError, ValueError):
            return []

    def _save(self) -> None:
        if not self.rules_path:
            return
        self.rules_path.parent.mkdir(parents=True, exist_ok=True)
        self.rules_path.write_text(json.dumps({"command_prefixes": self.allowed_prefixes}, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
