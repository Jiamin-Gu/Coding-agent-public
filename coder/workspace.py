"""工作区：agent 能访问的文件范围，所有路径都必须经过这里解析。"""
from pathlib import Path

# 遍历目录时跳过的目录，避免把依赖和缓存塞进上下文
IGNORED_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", ".idea",
    ".vscode", ".pytest_cache", ".mypy_cache", "dist", "build",
    ".coder",  # 团队模式的项目记忆，通过 memory / spec_section 工具读取
}


class WorkspaceError(Exception):
    """路径越界等工作区错误，消息会原样返回给模型。"""


class Workspace:
    def __init__(self, root: str | Path, read_guard: bool = True):
        self.root = Path(root).resolve()
        self.read_guard = read_guard  # 是否启用"先读后改"（评测时可以关掉做对比）
        # agent 读过（或自己写过）的文件 -> 当时的修改时间。用于"先读后改"检查
        self._seen: dict[Path, int] = {}

    def mark_seen(self, p: Path) -> None:
        self._seen[p] = p.stat().st_mtime_ns

    def seen_state(self, p: Path) -> str:
        """'unseen'：没读过；'stale'：读过但之后被修改了；'fresh'：读过且没变。"""
        if p not in self._seen:
            return "unseen"
        return "fresh" if self._seen[p] == p.stat().st_mtime_ns else "stale"

    def resolve(self, path: str) -> Path:
        """把模型给的路径转成绝对路径，并确保它没有逃出工作区（比如 ../../etc）。"""
        p = Path(path)
        if not p.is_absolute():
            p = self.root / p
        p = p.resolve()
        if not p.is_relative_to(self.root):
            raise WorkspaceError(f"路径 {path} 在工作区之外，禁止访问")
        return p

    def rel(self, p: Path) -> str:
        return p.relative_to(self.root).as_posix()
