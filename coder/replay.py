"""从评测轨迹重放出 agent 最终交付的代码，整理成成果示例。

    python -m coder.replay evals/results/<某次评测的目录> [--out examples/eval]

评测时每个任务在临时目录里运行，跑完就删除；但轨迹里完整记录了 agent 每一次写文件、改文件的内容。
重放 = 从任务的初始代码开始，按顺序重新执行那些成功的 write_file / edit_file。
重放后用隐藏测试再跑一遍：通过就说明重放出来的代码和当时 agent 交付的一致。

agent 用命令删除的文件（比如自检用的临时脚本）也会按时间顺序删掉：识别执行成功的 del / rm / Remove-Item /
os.remove 等命令里出现的文件名。其他命令副作用（比如脚本生成的文件）无法重放。
压缩过上下文的运行，早期的消息已经被摘要替换，无法完整重放，会被跳过。
团队模式的轨迹里有所有 agent 按时间顺序的操作日志（ops），直接按它重放，压缩过也不影响。
"""
import argparse
import fnmatch
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from . import use_utf8_output
from .eval import TASKS_DIR, TEST_DIR_NAME, TEST_TIMEOUT, run_hidden_tests
from .tools import build_tools
from .workspace import IGNORED_DIRS, Workspace

SUMMARY_MARK = "之前的对话已压缩为以下摘要"
SHELL_DELETE = re.compile(r"^\s*(?:del|erase|rm|rmdir|rd|Remove-Item)\b(.*)$", re.IGNORECASE)
PYTHON_DELETE = re.compile(r"(?:os\.remove|os\.unlink|shutil\.rmtree)\(\s*(['\"])(.+?)\1"
                           r"|Path\(\s*(['\"])(.+?)\3\s*\)\.unlink")


def deleted_targets(command: str) -> list[str]:
    """命令删除了哪些路径（可能含通配符）。只看删除命令自己的参数，避免把同一行里别处出现的文件名误判为删除。"""
    targets = []
    for segment in re.split(r"&&|\|\||[&;|\n]", command):
        m = SHELL_DELETE.match(segment)
        if m:
            targets += [t.strip("\"'") for t in m.group(1).split() if not t.startswith(("-", "/"))]
    for m in PYTHON_DELETE.finditer(command):
        targets.append(m.group(2) or m.group(4))
    return [t.replace("\\", "/") for t in targets if t]


def matches(path: str, target: str) -> bool:
    if "/" not in target:  # 只给了文件名：和任意目录下的同名文件比较
        return fnmatch.fnmatch(Path(path).name, target)
    return fnmatch.fnmatch(path, target.lstrip("./"))


def successful_steps(messages: list[dict]):
    """按顺序返回成功执行的 (工具名, 参数)：写文件、改文件，以及退出码为 0 的命令。"""
    calls = {}
    for m in messages:
        if m["role"] == "assistant":
            for c in m.get("tool_calls", []):
                calls[c["id"]] = c["function"]
        elif m["role"] == "tool":
            fn = calls.get(m["tool_call_id"])
            if not fn or m["content"].startswith(("错误", "用户拒绝")):
                continue
            if fn["name"] in ("write_file", "edit_file") or (
                    fn["name"] == "run_command" and m["content"].startswith("退出码：0")):
                yield fn["name"], json.loads(fn["arguments"] or "{}")


def successful_ops(ops: list[dict]):
    """团队模式：操作日志里只记录了成功的写入和命令，命令再按退出码筛选。"""
    for o in ops:
        if o["name"] in ("write_file", "edit_file") or (
                o["name"] == "run_command" and o["result"].startswith("退出码：0")):
            yield o["name"], o["args"]


def commands_run(messages: list[dict]) -> list[str]:
    return [json.loads(c["function"]["arguments"] or "{}").get("command", "")
            for m in messages if m["role"] == "assistant"
            for c in m.get("tool_calls", []) if c["function"]["name"] == "run_command"]


def snapshot(root: Path) -> dict[str, bytes]:
    out = {}
    for p in root.rglob("*"):
        if p.is_file() and not any(part in IGNORED_DIRS for part in p.relative_to(root).parts):
            out[p.relative_to(root).as_posix()] = p.read_bytes()
    return out


def replay(task: Path, trajectory: dict, code_dir: Path) -> list[str]:
    """重放到 code_dir，返回被 agent 用命令删除的文件。"""
    if code_dir.exists():
        shutil.rmtree(code_dir)
    code_dir.mkdir(parents=True)
    if (task / "setup").is_dir():
        shutil.copytree(task / "setup", code_dir, dirs_exist_ok=True)
    ws = Workspace(code_dir, read_guard=False)  # 重放时不需要"先读后改"检查
    tools = build_tools(ws)
    written: set[str] = set()
    deleted: list[str] = []
    team = trajectory.get("team")
    steps = successful_ops(team["ops"]) if team else successful_steps(trajectory["messages"])
    for name, args in steps:
        if name == "run_command":
            targets = deleted_targets(args.get("command", ""))
            for path in sorted(written):
                if any(matches(path, t) for t in targets) and (code_dir / path).is_file():
                    (code_dir / path).unlink()
                    written.discard(path)
                    deleted.append(path)
            continue
        tools[name].run(**args)
        written.add(Path(args["path"]).as_posix())
    return deleted


def verify(task: Path, code_dir: Path) -> tuple[bool, str]:
    """在临时副本里用隐藏测试复验，不往示例目录里留下测试和缓存。"""
    tmp = Path(tempfile.mkdtemp(prefix="coder-replay-"))
    try:
        shutil.copytree(code_dir, tmp, dirs_exist_ok=True)
        passed, output = run_hidden_tests(task, tmp)  # 和评测同样的判分方式（包括 task.json 里指定的测试命令）
        lines = [l for l in output.strip().splitlines() if l.strip()]
        return passed, (lines or [""])[-1]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def example_readme(task: Path, t: dict, changes: dict, passed: bool, test_line: str, run_dir: Path,
                   deleted: list[str]) -> str:
    r = t["result"]
    final = next((m["content"] for m in reversed(t["messages"]) if m["role"] == "assistant" and m.get("content")), "")
    team = t.get("team")
    cmds = [o["args"].get("command", "") for o in team["ops"] if o["name"] == "run_command"] if team         else commands_run(t["messages"])
    lines = [
        f"# {task.name}", "",
        f"由 Coding-agent 在评测中完成（模型 `{run_dir.name.split('-', 2)[-1]}`，评测 `{run_dir.name}`）。"
        "代码从评测轨迹重放得到，并用隐藏测试复验。", "",
        "## 任务", "", (task / "prompt.md").read_text(encoding="utf-8").strip(), "",
        "## 结果", "",
        f"- 隐藏测试复验：**{'通过' if passed else '未通过'}**（{test_line}）",
        f"- 调用模型 {r['steps']} 次，工具调用 {r['tool_calls']} 次（其中出错 {r['tool_errors']} 次），运行命令 {len(cmds)} 条，耗时 {r['seconds']:.0f} 秒",
        f"- token：输入 {r['prompt_tokens']:,}（命中缓存 {r['cached_tokens']:,}），输出 {r['completion_tokens']:,}", "",
        "## agent 新建或修改的文件", "",
    ]
    lines += [f"- `{path}`（{kind}）" for path, kind in sorted(changes.items())] or ["（无）"]
    if team:
        board = team["board"]
        decisions = [e for e in board["events"] if e["kind"] in ("decision", "question", "note")]
        lines += ["", "## 团队分工（团队模式）", "",
                  "主 agent 拆分的任务（每个任务由一个子 agent 完成，只能写自己负责的文件）：", ""]
        lines += [f"- **{tid}** [{x['status']}]：{', '.join(x['files'])}" for tid, x in board["tasks"].items()] or ["（主 agent 自己完成，没有拆分）"]
        if board["contracts"]:
            lines += ["", "接口契约：", ""] + [f"- **{n}**（{c['owner']}）：{c['text']}" for n, c in board["contracts"].items()]
        if decisions:
            lines += ["", "黑板上的决策和留言：", ""] + [f"- [{e['kind']}] {e['author']} → {e['to']}：{e['text']}" for e in decisions]
    if deleted:
        lines += ["", "agent 自检时写过、最后又用命令删除的临时文件（不包含在 code/ 里）："]
        lines += [f"- `{path}`" for path in deleted]
    lines += ["", "## agent 的总结", "", final.strip() or "（无）", ""]
    if cmds:
        lines += ["## 运行过的命令", "", "```"] + [c.splitlines()[0][:150] for c in cmds] + ["```", ""]
    return "\n".join(lines)


def write_index(out: Path) -> None:
    """汇总输出目录里的所有示例（每个示例有一份 meta.json），新的重放不会覆盖其他已有示例。"""
    metas = [json.loads(f.read_text(encoding="utf-8")) for f in sorted(out.glob("*/meta.json"))]
    index = ["# 评测成果示例", "",
             "Coding-agent 在评测中完成的任务。每个任务挑一次通过的运行，从轨迹重放出最终代码，并用隐藏测试复验。", "",
             "| 任务 | 复验 | 模型调用 | 输入 tokens | 输出 tokens | 耗时 | 新建/修改的文件 | 评测 |",
             "|---|---|---|---|---|---|---|---|"]
    for m in metas:
        index.append(f"| [{m['task']}]({m['task']}/README.md) | {'✅' if m['passed'] else '❌'} | {m['steps']} | "
                     f"{m['prompt']:,} | {m['completion']:,} | {m['seconds']:.0f}s | {m['files']} | `{m['run']}` |")
    (out / "README.md").write_text("\n".join(index) + "\n", encoding="utf-8")


def main() -> None:
    use_utf8_output()
    parser = argparse.ArgumentParser(description="从评测轨迹重放出 agent 交付的代码，整理成示例")
    parser.add_argument("run_dir", help="评测结果目录，例如 evals/results/20261002-024621-deepseek-flash")
    parser.add_argument("--out", default="examples/eval", help="输出目录")
    args = parser.parse_args()
    run_dir, out = Path(args.run_dir), Path(args.out)

    # 每个任务挑第一次通过、而且没有压缩过上下文的运行
    chosen: dict[str, dict] = {}
    for f in sorted((run_dir / "trajectories").glob("*.json")):
        t = json.loads(f.read_text(encoding="utf-8"))
        r = t["result"]
        compacted = not t.get("team") and (
            r.get("compactions") or any(SUMMARY_MARK in str(m.get("content")) for m in t["messages"]))
        if r["passed"] and not compacted and r["task"] not in chosen:
            chosen[r["task"]] = t

    for name, t in sorted(chosen.items()):
        task = TASKS_DIR / name
        code_dir = out / name / "code"
        deleted = replay(task, t, code_dir)
        before = snapshot(task / "setup") if (task / "setup").is_dir() else {}
        after = snapshot(code_dir)
        changes = {p: ("新建" if p not in before else "修改") for p, data in after.items() if before.get(p) != data}
        passed, test_line = verify(task, code_dir)
        (out / name / "README.md").write_text(example_readme(task, t, changes, passed, test_line, run_dir, deleted) + "\n",
                                              encoding="utf-8")
        r = t["result"]
        meta = {"task": name, "passed": passed, "steps": r["steps"], "prompt": r["prompt_tokens"],
                "completion": r["completion_tokens"], "seconds": r["seconds"], "files": len(changes),
                "run": run_dir.name}
        (out / name / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"{'✓' if passed else '✗'} {name}：{len(changes)} 个文件，{test_line}")
    write_index(out)
    print(f"\n已输出到 {out}")


if __name__ == "__main__":
    main()
