"""沙箱的工作区副本：开启沙箱时，agent 在工作区的副本上干活，真实项目在用户确认之前一个字节都不动。

以前沙箱只把命令放进容器，工作区是挂载进去的：工作区以外的东西受保护，但命令在 /workspace 里删、改文件，
真实项目跟着变，撤销也恢复不了（检查点只覆盖写文件工具的修改）。现在：
- 副本放在 ~/.coder/sandbox-copies/<对话 id>/，agent 的所有工具（读写文件、命令、团队模式、撤销）都在副本上，
  容器挂载的也是副本
- 每轮结束列出副本相对真实项目的改动（新增 / 修改 / 删除），用户选"应用到项目"或"放弃"
- 应用时，真实项目里某个文件在这期间被用户自己改过，就不覆盖它，列为冲突
- 没有待应用的改动时，下一轮开始前把用户在真实项目里的修改同步进副本

怎么知道谁改了什么：记一份"基准"——上次同步时真实项目里每个文件的哈希。副本和基准不一样 = agent 改的；
真实项目和基准不一样 = 用户改的。先比大小和修改时间，没变就不重新算哈希。

不复制 node_modules、.venv 这类依赖和缓存目录（需要时在容器里重新装，也不会同步回去）。.git 复制一份，让 agent
能看 git status / diff，但 .git 里的变化永远不同步回真实项目：提交由用户自己做。
"""
import hashlib
import json
import os
import shutil
from pathlib import Path

SKIP_DIRS = {"node_modules", ".venv", "venv", "env", "__pycache__", ".pytest_cache", ".mypy_cache",
             ".ruff_cache", ".tox", ".nox", ".cache"}
NO_SYNC = {".git"}  # 复制进副本，但不参与对比和同步


def _files(root: Path, skip_git: bool = True) -> dict[str, Path]:
    """root 下所有要跟踪的文件：{相对路径: 路径}。跳过依赖、缓存目录和符号链接。"""
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root)
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not (skip_git and d in NO_SYNC and rel_dir == Path("."))
                       and not os.path.islink(os.path.join(dirpath, d))]
        for name in filenames:
            p = Path(dirpath) / name
            if not p.is_symlink():
                out[(rel_dir / name).as_posix()] = p
    return out


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Shadow:
    def __init__(self, real: str | Path, copy: str | Path):
        self.real, self.copy = Path(real).resolve(), Path(copy).resolve()
        self.state_file = self.copy.parent / f"{self.copy.name}.json"
        self.base: dict[str, str] = {}      # 基准：上次同步时真实项目的 {路径: 哈希}
        self.stats: dict[str, list] = {}    # {"real:路径" / "copy:路径": [大小, 修改时间, 哈希]}，免得每次重算

    # ---------- 准备

    def ensure(self) -> None:
        """副本不存在就整份复制；存在就读回基准（服务重启后，没应用的改动还在）。"""
        if self.copy.is_dir() and self.state_file.is_file():
            try:
                data = json.loads(self.state_file.read_text(encoding="utf-8"))
                self.base, self.stats = data.get("base", {}), data.get("stats", {})
                return
            except ValueError:
                pass
        shutil.rmtree(self.copy, ignore_errors=True)
        self.copy.mkdir(parents=True, exist_ok=True)
        git = self.real / ".git"
        if git.is_dir():
            shutil.copytree(git, self.copy / ".git", symlinks=True, dirs_exist_ok=True)
        self.base = {}
        for rel, p in _files(self.real).items():
            self._copy_file(p, self.copy / rel)
            self.base[rel] = self._digest("real", rel, p)
            self._digest("copy", rel, self.copy / rel)
        self._save()

    def remove(self) -> None:
        shutil.rmtree(self.copy, ignore_errors=True)
        self.state_file.unlink(missing_ok=True)

    def _save(self) -> None:
        self.state_file.write_text(json.dumps({"real": str(self.real), "base": self.base, "stats": self.stats}),
                                   encoding="utf-8")

    @staticmethod
    def _copy_file(src: Path, dst: Path) -> None:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    def _digest(self, side: str, rel: str, p: Path) -> str:
        st = p.stat()
        key = f"{side}:{rel}"
        cached = self.stats.get(key)
        if cached and cached[0] == st.st_size and cached[1] == st.st_mtime_ns:
            return cached[2]
        sha = _sha(p)
        self.stats[key] = [st.st_size, st.st_mtime_ns, sha]
        return sha

    # ---------- 对比

    def changes(self) -> dict[str, list[str]]:
        """agent 在副本里做的改动（相对基准）。"""
        now = {rel: self._digest("copy", rel, p) for rel, p in _files(self.copy).items()}
        out = {"added": sorted(r for r in now if r not in self.base),
               "modified": sorted(r for r in now if r in self.base and now[r] != self.base[r]),
               "deleted": sorted(r for r in self.base if r not in now)}
        self._save()
        return out

    def pending(self) -> bool:
        return any(self.changes().values())

    def _real_now(self, rel: str) -> str | None:
        p = self.real / rel
        return self._digest("real", rel, p) if p.is_file() else None

    # ---------- 应用 / 放弃 / 同步

    def apply(self) -> dict[str, list[str]]:
        """把改动同步回真实项目。真实项目里这个文件在这期间被用户改过的，不覆盖，列为冲突。"""
        ch, done, conflicts = self.changes(), [], []
        for rel in ch["added"] + ch["modified"] + ch["deleted"]:
            real_now = self._real_now(rel)
            if real_now != self.base.get(rel):  # 用户在真实项目里也改了这个文件（或者新建、删除了）
                conflicts.append(rel)
                continue
            if rel in ch["deleted"]:
                (self.real / rel).unlink(missing_ok=True)
                self.base.pop(rel, None)
                self.stats.pop(f"real:{rel}", None)
            else:
                self._copy_file(self.copy / rel, self.real / rel)
                self.base[rel] = self._digest("real", rel, self.real / rel)
            done.append(rel)
        self._save()
        return {"applied": done, "conflicts": conflicts}

    def discard(self) -> list[str]:
        """放弃改动：副本恢复成真实项目现在的样子。返回恢复了哪些文件。"""
        ch, restored = self.changes(), []
        for rel in ch["added"] + ch["modified"] + ch["deleted"]:
            real = self.real / rel
            if real.is_file():
                self._copy_file(real, self.copy / rel)
                self.base[rel] = self._digest("real", rel, real)
                self._digest("copy", rel, self.copy / rel)
            else:
                (self.copy / rel).unlink(missing_ok=True)
                self.base.pop(rel, None)
                self.stats.pop(f"copy:{rel}", None)
            restored.append(rel)
        self._save()
        return restored

    def refresh(self) -> list[str]:
        """没有待应用的改动时：把用户在真实项目里的修改同步进副本。返回同步了哪些文件。"""
        if self.pending():
            return []
        real_files = _files(self.real)
        synced = []
        for rel, p in real_files.items():
            sha = self._digest("real", rel, p)
            if self.base.get(rel) != sha:
                self._copy_file(p, self.copy / rel)
                self.base[rel] = sha
                self._digest("copy", rel, self.copy / rel)
                synced.append(rel)
        for rel in [r for r in self.base if r not in real_files]:
            (self.copy / rel).unlink(missing_ok=True)
            self.base.pop(rel)
            synced.append(rel)
        self._save()
        return synced


def describe(ch: dict[str, list[str]], limit: int = 12) -> str:
    """改动的文字说明：新增 2 个、修改 1 个、删除 0 个，后面列出文件。"""
    parts = [f"{label} {len(ch[k])} 个" for k, label in (("added", "新增"), ("modified", "修改"), ("deleted", "删除")) if ch[k]]
    names = [f"+{r}" for r in ch["added"]] + [f"~{r}" for r in ch["modified"]] + [f"-{r}" for r in ch["deleted"]]
    more = f" 等 {len(names)} 个" if len(names) > limit else ""
    return "、".join(parts) + ("：" + "，".join(names[:limit]) + more if names else "")
