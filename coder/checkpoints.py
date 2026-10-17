"""检查点：每轮任务开始时建一个检查点，agent 第一次写某个文件之前先备份原样。撤销时把这一轮改过的文件恢复原样
（新建的文件删除）。

只覆盖 write_file / edit_file 的修改。run_command 的副作用（生成文件、安装依赖、改数据库）无法撤销，界面上会说明。
如果撤销时发现文件在这一轮之后又被改过（用户手动编辑，或者命令改的），不覆盖它，列出来让用户自己决定。
"""
import hashlib
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

MAX_CHECKPOINTS = 20


def _digest(p: Path) -> str | None:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None


@dataclass
class Checkpoint:
    label: str
    created: float = field(default_factory=time.time)
    originals: dict[str, bytes | None] = field(default_factory=dict)  # 相对路径 -> 本轮第一次写之前的内容（None=原来不存在）
    after: dict[str, str | None] = field(default_factory=dict)        # 相对路径 -> agent 最后一次写完后的哈希


class Checkpoints:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.stack: list[Checkpoint] = []
        self.lock = threading.Lock()  # 团队模式里多个子 agent 同时写文件

    def begin(self, label: str) -> None:
        with self.lock:
            if self.stack and not self.stack[-1].after:
                self.stack.pop()  # 上一轮没改任何文件，不占一个撤销位置
            self.stack.append(Checkpoint(label[:80]))
            del self.stack[:-MAX_CHECKPOINTS]

    def _rel(self, p: Path) -> str:
        return p.resolve().relative_to(self.root).as_posix()

    def before_write(self, p: Path) -> None:
        """agent 写文件之前调用：这一轮第一次写这个文件时备份原内容。"""
        with self.lock:
            if not self.stack:
                self.stack.append(Checkpoint("（未命名）"))
            cp, rel = self.stack[-1], self._rel(p)
            if rel not in cp.originals:
                cp.originals[rel] = p.read_bytes() if p.is_file() else None

    def after_write(self, p: Path) -> None:
        with self.lock:
            if self.stack:
                self.stack[-1].after[self._rel(p)] = _digest(p)

    def last(self) -> Checkpoint | None:
        with self.lock:
            for cp in reversed(self.stack):
                if cp.after:
                    return cp
            return None

    def undo(self, force: bool = False) -> dict:
        """撤销最近一个改过文件的检查点。返回 {label, restored, deleted, conflicts}；
        有冲突且不强制时什么都不改，检查点保留。"""
        with self.lock:
            while self.stack and not self.stack[-1].after:
                self.stack.pop()
            if not self.stack:
                return {"label": "", "restored": [], "deleted": [], "conflicts": []}
            cp = self.stack[-1]
            conflicts = [rel for rel, h in cp.after.items() if _digest(self.root / rel) != h]
            result = {"label": cp.label, "restored": [], "deleted": [], "conflicts": conflicts}
            if conflicts and not force:
                return result
            for rel in cp.after:  # 备份了但没写成功的文件没有变化，不用动
                data, p = cp.originals[rel], self.root / rel
                if data is None:
                    if p.is_file():
                        p.unlink()
                        result["deleted"].append(rel)
                else:
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(data)
                    result["restored"].append(rel)
            self.stack.pop()
            return result


def describe(result: dict) -> str:
    """给用户看的撤销结果。"""
    if not result["label"]:
        return "没有可以撤销的文件修改"
    if result["conflicts"] and not (result["restored"] or result["deleted"]):
        return ("没有撤销：这些文件在那一轮之后又被修改过（可能是你手动改的，或命令改的），撤销会覆盖这些修改：\n  "
                + "\n  ".join(result["conflicts"]) + "\n确定要撤销请用强制撤销")
    lines = [f"已撤销「{result['label']}」这一轮的文件修改"]
    if result["restored"]:
        lines.append("恢复：" + "、".join(result["restored"]))
    if result["deleted"]:
        lines.append("删除（这一轮新建的）：" + "、".join(result["deleted"]))
    lines.append("注意：命令（run_command）产生的效果无法撤销")
    return "\n".join(lines)


def agent_note(result: dict) -> str:
    """告诉模型：用户撤销了上一轮的修改，文件已经回到之前的样子。"""
    parts = []
    if result["restored"]:
        parts.append("restored " + ", ".join(result["restored"]))
    if result["deleted"]:
        parts.append("deleted " + ", ".join(result["deleted"]))
    return ("[The user undid your file changes from the turn \"" + result["label"] + "\": " + "; ".join(parts)
            + ". Those files are back to their earlier content; re-read them before editing.]")
