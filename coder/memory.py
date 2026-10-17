"""团队模式的项目记忆：存在工作区的 .coder/memory/ 里，上下文压缩、子 agent 交接、服务重启都不会丢。

项目大了以后，主 agent 不可能把需求、所有代码和测试同时放在上下文里。做法是分层：
- 主 agent 平时只看"摘要版"：需求目录、每个模块的卡片、契约和任务看板，需要细节时再按需读原文
- 子 agent 拿到自己子任务的"完整版"：相关需求小节的原文、要改的文件全文、所依赖模块的接口

三类记忆：
1. 需求索引：按 Markdown 标题把需求文档切成小节，每节有编号（S1、S2……）。切分由程序完成，原文一字不改
2. 模块卡片：每个代码文件一张卡。对外接口（类、函数签名）和依赖关系由程序从代码里提取，不经过模型转述；
   说明取自模块开头的文档字符串；另外记录负责它的任务和对应的需求小节
3. 黑板：契约、决策、任务状态（见 team.py），每次变化都写进文件

能用程序提取的一律程序提取，模型写的内容（文档字符串）只当目录用，原文永远以文件为准。
"""
import ast
import json
import re
import sys
import threading
from pathlib import Path

STDLIB = set(sys.stdlib_module_names)

MEMORY_DIR = ".coder/memory"
HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*#*\s*$")
OVERVIEW_CHARS = 12_000  # 主 agent 的记忆总览最多这么长，超出时截断卡片列表


def split_sections(text: str) -> list[dict]:
    """按一到三级标题切分 Markdown。标题之前的内容算作第 0 节（如果有）。代码块里的 # 不算标题。"""
    lines = text.splitlines()
    sections: list[dict] = []
    current = {"title": "（开头）", "level": 0, "start": 1, "lines": []}
    in_code = False
    for no, line in enumerate(lines, 1):
        if line.lstrip().startswith("```"):
            in_code = not in_code
        m = None if in_code else HEADING.match(line)
        if m:
            if current["lines"] and any(x.strip() for x in current["lines"]) or current["level"]:
                sections.append(current)
            current = {"title": m.group(2), "level": len(m.group(1)), "start": no, "lines": [line]}
        else:
            current["lines"].append(line)
    sections.append(current)
    out = []
    for i, s in enumerate(sections, 1):
        body = "\n".join(s["lines"]).strip("\n")
        first = next((x.strip() for x in s["lines"][1 if s["level"] else 0:] if x.strip()), "")
        out.append({"id": f"S{i}", "title": s["title"], "level": s["level"], "start": s["start"],
                    "end": s["start"] + len(s["lines"]) - 1, "chars": len(body), "first": first[:80], "text": body})
    return out


def module_card(path: str, source: str) -> dict:
    """从 Python 源码提取模块卡片：说明、对外接口、项目内依赖。解析失败时只记录大小。"""
    card = {"path": path, "summary": "", "interface": [], "imports": [], "lines": source.count("\n") + 1}
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        card["summary"] = f"（语法错误，无法解析：第 {e.lineno} 行）"
        return card
    doc = ast.get_docstring(tree)
    card["summary"] = (doc or "").strip().splitlines()[0][:160] if doc else ""
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            card["interface"].append(_signature(node))
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            bases = ", ".join(ast.unparse(b) for b in node.bases)
            methods = [_signature(n, method=True) for n in node.body
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                       and (not n.name.startswith("_") or n.name == "__init__")]
            card["interface"].append(f"class {node.name}({bases})" + (": " + "; ".join(methods) if methods else ""))
        elif isinstance(node, ast.Assign) and all(isinstance(t, ast.Name) and t.id.isupper() for t in node.targets):
            card["interface"].append(", ".join(t.id for t in node.targets) + " = …")
        if isinstance(node, ast.ImportFrom) and (node.level or (node.module or "").split(".")[0] not in STDLIB):
            mod = "." * node.level + (node.module or "")  # 只记项目内的依赖，标准库不算
            card["imports"].append(f"{mod}: {', '.join(a.name for a in node.names)}")
    return card


def _signature(node, method=False) -> str:
    args = ast.unparse(node.args)
    if method and args.startswith("self"):
        args = args[4:].lstrip(", ")
    ret = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    prefix = "" if method else "def "
    return f"{prefix}{node.name}({args}){ret}"


def render_card(card: dict) -> str:
    head = f"### {card['path']}（{card['lines']} 行"
    head += f"，任务 {card['task']}" if card.get("task") else ""
    head += f"，需求 {', '.join(card['spec'])}" if card.get("spec") else ""
    lines = [head + "）"]
    if card.get("summary"):
        lines.append(card["summary"])
    lines += [f"- {x}" for x in card["interface"]]
    if card.get("imports"):
        lines.append("依赖：" + "；".join(card["imports"]))
    return "\n".join(lines)


class ProjectMemory:
    """一个工作区的项目记忆。线程安全：多个子 agent 并行完成时会同时更新卡片。"""

    def __init__(self, root):
        self.root = Path(root)
        self.dir = self.root / MEMORY_DIR
        self.lock = threading.RLock()  # 可重入：保存时会生成总览，总览也要加锁
        self.specs: dict[str, list[dict]] = {}   # 需求文档路径 -> 小节
        self.cards: dict[str, dict] = {}         # 文件路径 -> 卡片
        self.board: dict = {}                    # 黑板的最新快照
        self._load()

    # ---------- 需求索引

    def index_doc(self, rel_path: str) -> list[dict]:
        text = (self.root / rel_path).read_text(encoding="utf-8", errors="replace")
        sections = split_sections(text)
        with self.lock:
            self.specs[rel_path] = sections
            self._save()
        return sections

    def outline(self) -> str:
        """需求目录：编号、标题、第一句、长度。主 agent 看这个，需要细节时用 spec_section 读原文。"""
        out = []
        for path, sections in self.specs.items():
            out.append(f"## {path}")
            for s in sections:
                indent = "  " * max(s["level"] - 1, 0)
                out.append(f"{indent}- {s['id']} {s['title']}（{s['chars']} 字）：{s['first']}")
        return "\n".join(out)

    def sections(self, ids: list[str]) -> tuple[str, list[str]]:
        """返回这些小节的原文，以及找不到的编号。"""
        index = {s["id"]: s for sections in self.specs.values() for s in sections}
        found = [index[i] for i in dict.fromkeys(ids) if i in index]
        missing = [i for i in ids if i not in index]
        return "\n\n".join(f"<!-- {s['id']} -->\n{s['text']}" for s in found), missing

    # ---------- 模块卡片

    def update_card(self, rel_path: str, task: str = "", spec: list[str] | None = None) -> dict | None:
        p = self.root / rel_path
        if not p.is_file():
            with self.lock:
                self.cards.pop(rel_path, None)
                self._save()
            return None
        source = p.read_text(encoding="utf-8", errors="replace")
        if rel_path.endswith(".py"):
            card = module_card(rel_path, source)
        else:
            first = next((x.strip() for x in source.splitlines() if x.strip()), "")
            card = {"path": rel_path, "summary": first[:160], "interface": [], "imports": [],
                    "lines": source.count("\n") + 1}
        card["task"], card["spec"] = task, list(spec or [])
        with self.lock:
            self.cards[rel_path] = card
            self._save()
        return card

    def cards_for(self, paths: list[str]) -> str:
        with self.lock:
            return "\n\n".join(render_card(self.cards[p]) for p in paths if p in self.cards)

    # ---------- 黑板

    def save_board(self, board: dict) -> None:
        with self.lock:
            self.board = board
            self._save()

    # ---------- 总览与持久化

    def overview(self) -> str:
        """主 agent 的记忆总览：需求目录 + 所有模块卡片 + 契约 + 任务看板。上下文压缩后靠它恢复全局。"""
        with self.lock:
            board, cards = self.board, list(self.cards.values())
        parts = ["# 项目记忆（摘要版；细节请读原文：spec_section 读需求小节，read_file 读代码）"]
        if self.specs:
            parts += ["## 需求目录", self.outline()]
        if board.get("contracts"):
            parts.append("## 契约")
            parts += [f"- {n}（{c['owner']}）：{c['text']}" for n, c in board["contracts"].items()]
        if board.get("tasks"):
            parts.append("## 任务")
            for tid, t in board["tasks"].items():
                parts.append(f"- {tid} [{t['status']}] 文件：{', '.join(t['files'])}"
                             + (f"；需求：{', '.join(t.get('spec_sections', []))}" if t.get("spec_sections") else ""))
        if cards:
            parts.append("## 模块卡片")
            parts += [render_card(c) for c in sorted(cards, key=lambda c: c["path"])]
        text = "\n".join(parts)
        if len(text) > OVERVIEW_CHARS:
            text = text[:OVERVIEW_CHARS] + "\n…（总览太长已截断，用 read_file 查看具体文件）"
        return text

    def _save(self) -> None:
        """写进 .coder/memory/：JSON 给程序读，MEMORY.md 给人看。调用方已经持有锁。"""
        self.dir.mkdir(parents=True, exist_ok=True)
        data = {"specs": {p: [{k: v for k, v in s.items() if k != "text"} for s in secs]
                          for p, secs in self.specs.items()},
                "cards": self.cards, "board": self.board}
        (self.dir / "memory.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        (self.dir / "MEMORY.md").write_text(self.overview() + "\n", encoding="utf-8")

    def _load(self) -> None:
        """已有记忆就读回来（比如服务重启后继续同一个项目）。需求小节的原文从文档重新切分，保证和文件一致。"""
        path = self.dir / "memory.json"
        if not path.is_file():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self.cards, self.board = data.get("cards", {}), data.get("board", {})
        for doc in data.get("specs", {}):
            if (self.root / doc).is_file():
                self.specs[doc] = split_sections((self.root / doc).read_text(encoding="utf-8", errors="replace"))
