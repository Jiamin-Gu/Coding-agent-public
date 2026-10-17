"""文件系统工具：列目录、读、写、精确编辑、搜索。"""
import difflib
import fnmatch
import os
import re
from pathlib import Path

from ..workspace import IGNORED_DIRS
from .base import Tool, ToolError

MAX_FILE_BYTES = 1_000_000


def is_binary(path: Path) -> bool:
    with open(path, "rb") as f:
        return b"\0" in f.read(8000)


def read_text(path: Path) -> tuple[str, str]:
    """读取文本，统一换行为 \\n，同时返回原文件的换行风格，写回时保持不变。"""
    raw = path.read_bytes()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    text = raw.decode("utf-8", errors="replace").replace("\r\n", "\n")
    return text, newline


def write_text(path: Path, text: str, newline: str = "\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline=newline) as f:
        f.write(text)


def make_diff(old: str, new: str, name: str) -> str:
    diff = difflib.unified_diff(
        old.splitlines(keepends=True), new.splitlines(keepends=True),
        fromfile=f"a/{name}", tofile=f"b/{name}",
    )
    return "".join(diff) or "(无变化)"


class ListDir(Tool):
    name = "list_dir"
    description = "列出目录内容，目录名以 / 结尾。会自动跳过 .git、node_modules 等目录。"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "相对工作区的路径，默认为根目录", "default": "."},
            "depth": {"type": "integer", "description": "递归深度，1-3，默认 1", "default": 1},
        },
    }
    MAX_ENTRIES = 300

    def run(self, path: str = ".", depth: int = 1) -> str:
        root = self.ws.resolve(path)
        if not root.is_dir():
            raise ToolError(f"{path} 不是目录")
        depth = max(1, min(depth, 3))
        lines: list[str] = []

        def walk(d: Path, level: int):
            for entry in sorted(d.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
                if len(lines) >= self.MAX_ENTRIES:
                    return
                if entry.is_dir():
                    if entry.name in IGNORED_DIRS:
                        continue
                    lines.append("  " * level + entry.name + "/")
                    if level + 1 < depth:
                        walk(entry, level + 1)
                else:
                    lines.append("  " * level + entry.name)

        walk(root, 0)
        if len(lines) >= self.MAX_ENTRIES:
            lines.append(f"...（超过 {self.MAX_ENTRIES} 项，已截断）")
        return "\n".join(lines) or "(空目录)"


class ReadFile(Tool):
    name = "read_file"
    description = (
        "读取文本文件，返回带行号的内容。大文件请用 offset/limit 分段读取。"
        "修改文件前必须先读取它。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "offset": {"type": "integer", "description": "起始行号（从 1 开始），默认 1", "default": 1},
            "limit": {"type": "integer", "description": "最多读取行数，默认 400", "default": 400},
        },
        "required": ["path"],
    }

    def run(self, path: str, offset: int = 1, limit: int = 400) -> str:
        p = self.ws.resolve(path)
        if not p.is_file():
            raise ToolError(f"文件不存在：{path}")
        if p.stat().st_size > MAX_FILE_BYTES * 5:
            raise ToolError("文件过大，请用 grep 定位后再分段读取")
        if is_binary(p):
            raise ToolError(f"{path} 是二进制文件")
        lines = read_text(p)[0].split("\n")
        self.ws.mark_seen(p)
        start = max(offset, 1) - 1
        chunk = lines[start:start + limit]
        out = "\n".join(f"{i:>6}\t{line}" for i, line in enumerate(chunk, start + 1))
        end = start + len(chunk)
        if end < len(lines):
            out += f"\n（共 {len(lines)} 行，已显示 {start + 1}-{end} 行，可用 offset={end + 1} 继续读取）"
        return out or "(空文件)"


class WriteFile(Tool):
    name = "write_file"
    description = "创建新文件，或完整覆盖文件内容。修改已有文件请优先使用 edit_file。"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "content": {"type": "string", "description": "完整的文件内容"},
        },
        "required": ["path", "content"],
    }
    needs_permission = True

    def preview(self, path: str, content: str) -> str:
        p = self.ws.resolve(path)
        if p.is_file():
            require_fresh(self.ws, p, path)
            return make_diff(read_text(p)[0], content, path)
        lines = content.split("\n")
        head = "\n".join(lines[:30])
        more = f"\n...（共 {len(lines)} 行）" if len(lines) > 30 else ""
        return f"新建文件 {path}：\n{head}{more}"

    def run(self, path: str, content: str) -> str:
        p = self.ws.resolve(path)
        existed = p.is_file()
        if existed:
            require_fresh(self.ws, p, path)
        newline = read_text(p)[1] if existed else "\n"
        write_text(p, content, newline)
        self.ws.mark_seen(p)  # 自己刚写的内容，相当于已经读过
        return f"已{'覆盖' if existed else '创建'} {path}（{len(content.splitlines())} 行）"


def require_fresh(ws, p: Path, path: str) -> None:
    """先读后改：不允许修改没读过、或读过之后又被别处改动的文件，避免基于猜测或过期内容修改。"""
    if not ws.read_guard:
        return
    state = ws.seen_state(p)
    if state == "unseen":
        raise ToolError(f"修改已有文件 {path} 之前，必须先用 read_file 读取它")
    if state == "stale":
        raise ToolError(f"{path} 在你上次读取之后被修改过（可能是命令或用户改的），请重新 read_file 后再修改")


def apply_edit(text: str, old: str, new: str, replace_all: bool) -> str:
    if old == new:
        raise ToolError("old_string 和 new_string 相同，无需修改")
    count = text.count(old)
    if count == 0:
        raise ToolError(
            "在文件中找不到 old_string。请先用 read_file 确认文件当前内容，"
            "注意缩进和空白必须完全一致（不要包含行号前缀）。"
        )
    if count > 1 and not replace_all:
        raise ToolError(
            f"old_string 在文件中出现了 {count} 次，无法确定改哪一处。"
            "请在 old_string 中加入更多上下文使其唯一，或设置 replace_all=true。"
        )
    return text.replace(old, new) if replace_all else text.replace(old, new, 1)


class EditFile(Tool):
    name = "edit_file"
    description = (
        "精确替换文件中的一段文本：把 old_string 替换成 new_string。"
        "old_string 必须与文件内容逐字符一致（包括缩进），并且在文件中唯一。"
        "这比重写整个文件更省 token，也不会误改其他地方。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "old_string": {"type": "string", "description": "要被替换的原文本"},
            "new_string": {"type": "string", "description": "替换后的新文本"},
            "replace_all": {"type": "boolean", "description": "是否替换所有出现处，默认 false", "default": False},
        },
        "required": ["path", "old_string", "new_string"],
    }
    needs_permission = True

    def _load(self, path: str) -> tuple[Path, str, str]:
        p = self.ws.resolve(path)
        if not p.is_file():
            raise ToolError(f"文件不存在：{path}。新建文件请用 write_file")
        require_fresh(self.ws, p, path)
        text, newline = read_text(p)
        return p, text, newline

    def preview(self, path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
        _, text, _ = self._load(path)
        return make_diff(text, apply_edit(text, old_string, new_string, replace_all), path)

    def run(self, path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
        p, text, newline = self._load(path)
        write_text(p, apply_edit(text, old_string, new_string, replace_all), newline)
        self.ws.mark_seen(p)
        return f"已修改 {path}"


class Grep(Tool):
    name = "grep"
    description = "用正则表达式搜索文件内容，返回 文件:行号: 内容。用于定位函数定义、引用等。"
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Python 正则表达式"},
            "path": {"type": "string", "description": "搜索的目录或文件，默认为根目录", "default": "."},
            "include": {"type": "string", "description": "文件名过滤，如 *.py"},
        },
        "required": ["pattern"],
    }
    MAX_MATCHES = 100

    def run(self, pattern: str, path: str = ".", include: str | None = None) -> str:
        try:
            regex = re.compile(pattern)
        except re.error as e:
            raise ToolError(f"正则表达式无效：{e}")
        root = self.ws.resolve(path)
        files = [root] if root.is_file() else self._iter_files(root, include)
        matches: list[str] = []
        for f in files:
            if f.stat().st_size > MAX_FILE_BYTES or is_binary(f):
                continue
            for i, line in enumerate(read_text(f)[0].split("\n"), 1):
                if regex.search(line):
                    matches.append(f"{self.ws.rel(f)}:{i}: {line.strip()[:200]}")
                    if len(matches) >= self.MAX_MATCHES:
                        return "\n".join(matches) + f"\n...（超过 {self.MAX_MATCHES} 条，请缩小搜索范围）"
        return "\n".join(matches) or "没有匹配结果"

    def _iter_files(self, root: Path, include: str | None):
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS]
            for name in sorted(filenames):
                if include and not fnmatch.fnmatch(name, include):
                    continue
                yield Path(dirpath) / name
