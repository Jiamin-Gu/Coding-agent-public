"""分析一次评测的 token 账本：钱花在哪里、哪些是浪费。

    python -m coder.analyze evals/results/<某次评测的目录>

输出：
- 上下文构成：系统提示、工具定义、用户消息、助手消息、工具结果各占输入 token 的多少
- 上下文随步数的增长：第 1、5、10、20 步时平均的输入大小
- 可能的浪费：同一次运行里重复读取同一个文件、重复执行完全相同的命令
- 通过与失败的运行在成本上的差别
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from . import use_utf8_output


def load_runs(run_dir: Path) -> list[dict]:
    runs = []
    for f in sorted((run_dir / "trajectories").glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        data["name"] = f.stem
        runs.append(data)
    return runs


def tool_calls(messages: list[dict]):
    for m in messages:
        for c in m.get("tool_calls", []) if m.get("role") == "assistant" else []:
            try:
                args = json.loads(c["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {}
            yield c["function"]["name"], args


def analyze(run_dir: Path) -> str:
    runs = load_runs(run_dir)
    if not runs:
        return f"{run_dir} 里没有轨迹文件"
    lines = [f"# token 账本分析：{run_dir.name}", "", f"共 {len(runs)} 次运行。", ""]

    # 1. 上下文构成（按估算值的比例，乘以实际输入 token）
    parts = defaultdict(float)
    total_prompt = 0
    for r in runs:
        for c in r.get("call_log", []):
            comp = c["composition"]
            est = sum(comp.values()) or 1
            for k, v in comp.items():
                parts[k] += c["prompt"] * v / est
            total_prompt += c["prompt"]
    names = {"system": "系统提示", "tools": "工具定义", "user": "用户消息（任务）",
             "assistant": "助手消息（含工具调用参数）", "tool_results": "工具结果"}
    lines += ["## 输入 token 的构成", "", "| 部分 | 占比 | 约多少 token |", "|---|---|---|"]
    for k, v in sorted(parts.items(), key=lambda x: -x[1]):
        lines.append(f"| {names.get(k, k)} | {v / max(total_prompt, 1):.0%} | {v:,.0f} |")

    # 2. 上下文随步数增长
    by_step = defaultdict(list)
    for r in runs:
        for c in r.get("call_log", []):
            by_step[c["step"]].append(c["prompt"])
    lines += ["", "## 每一步的输入大小（所有运行的平均）", ""]
    for s in (1, 3, 5, 10, 15, 20, 30):
        if by_step.get(s):
            lines.append(f"- 第 {s} 步：{sum(by_step[s]) / len(by_step[s]):,.0f} token（{len(by_step[s])} 次运行走到这一步）")
    calls = sum(len(r.get("call_log", [])) for r in runs)
    uncached = sum(c["prompt"] - c["cached"] for r in runs for c in r.get("call_log", []))
    lines.append(f"- 平均每次调用输入 {total_prompt / max(calls, 1):,.0f} token，其中未命中缓存 {uncached / max(calls, 1):,.0f}")

    # 3. 可能的浪费
    reread, rerun, reread_runs, rerun_runs = 0, 0, 0, 0
    examples = []
    for r in runs:
        reads, cmds = Counter(), Counter()
        for name, args in tool_calls(r["messages"]):
            if name == "read_file":
                reads[(args.get("path"), args.get("offset", 1), args.get("limit", 400))] += 1
            elif name == "run_command":
                cmds[args.get("command", "")] += 1
        extra_reads = sum(n - 1 for n in reads.values() if n > 1)
        extra_cmds = sum(n - 1 for n in cmds.values() if n > 1)
        reread += extra_reads
        rerun += extra_cmds
        reread_runs += extra_reads > 0
        rerun_runs += extra_cmds > 0
        if extra_cmds >= 2:
            cmd, n = cmds.most_common(1)[0]
            examples.append(f"{r['name']}：`{cmd[:80]}` 执行了 {n} 次")
    lines += ["", "## 可能的浪费", "",
              f"- 重复读取同一个文件的同一段：共 {reread} 次，出现在 {reread_runs}/{len(runs)} 次运行中"
              "（注意：文件被修改后重新读取是必要的，这里只是上限）",
              f"- 重复执行完全相同的命令：共 {rerun} 次，出现在 {rerun_runs}/{len(runs)} 次运行中"
              "（改代码后重跑测试是必要的，这里同样只是上限）"]
    lines += [f"  - {e}" for e in examples[:8]]

    # 4. 通过和失败的成本
    lines += ["", "## 通过与失败的运行", ""]
    for passed in (True, False):
        rs = [r for r in runs if r["result"]["passed"] is passed]
        if rs:
            avg = lambda k: sum(r["result"][k] for r in rs) / len(rs)
            lines.append(f"- {'通过' if passed else '失败'}（{len(rs)} 次）：平均调用模型 {avg('steps'):.1f} 次，"
                         f"输入 {avg('prompt_tokens'):,.0f}，输出 {avg('completion_tokens'):,.0f}")
    return "\n".join(lines)


def main() -> None:
    use_utf8_output()
    if len(sys.argv) != 2:
        sys.exit("用法：python -m coder.analyze <评测结果目录>")
    report = analyze(Path(sys.argv[1]))
    print(report)
    out = Path(sys.argv[1]) / "analysis.md"
    out.write_text(report + "\n", encoding="utf-8")
    print(f"\n已保存到 {out}")


if __name__ == "__main__":
    main()
