"""评测：让 agent 在隔离的临时目录里完成任务，再用它看不到的隐藏测试自动判分。

    python -m coder.eval                    # 跑全部任务
    python -m coder.eval --tasks bug        # 只跑名字包含 bug 的任务
    python -m coder.eval --repeat 3         # 每个任务跑 3 次，看稳定性
    python -m coder.eval --no-read-guard    # 消融实验：关闭"先读后改"
    python -m coder.eval --validate         # 不调用模型，用参考答案校验评测集本身

任务目录 evals/tasks/<任务名>/：
    prompt.md   交给 agent 的任务描述
    setup/      初始代码（可选），复制到工作区
    tests/      隐藏测试，agent 完成后才复制进工作区（_eval_tests/）并运行
    solution/   参考答案（只用于 --validate，agent 看不到）
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from . import __version__, use_utf8_output
from .agent import Agent
from .config import Config
from .permissions import PermissionManager
from .store import Store
from .team import Team, team_messages
from .sandbox import DockerSandbox
from .tools import ProcessManager, build_tools
from .workspace import Workspace

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TASKS_DIR = PROJECT_ROOT / "evals" / "tasks"
RESULTS_DIR = PROJECT_ROOT / "evals" / "results"
TEST_DIR_NAME = "_eval_tests"
TEST_TIMEOUT = 120


@dataclass
class Result:
    task: str
    passed: bool = False
    steps: int = 0              # 调用模型的次数
    tool_calls: int = 0
    tool_errors: int = 0        # 工具返回错误的次数（参数错误、编辑匹配失败等）
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    compactions: int = 0
    llm_retries: int = 0        # 网络超时等临时错误导致的模型调用重试次数
    seconds: float = 0.0
    error: str = ""             # agent 运行中的异常（比如 API 失败）
    test_output: str = field(default="", repr=False)


class RecordingUI:
    """评测时统计工具调用；verbose 时实时打印每一步，方便盯长任务。"""

    def __init__(self, task: str = "", verbose: bool = False):
        self.tool_calls = 0
        self.tool_errors = 0
        self.task, self.verbose = task, verbose
        self._lock = threading.Lock()

    def tool_call(self, name, args, who: str = ""):
        with self._lock:  # 团队模式下多个子 agent 并行调用
            self.tool_calls += 1
            if self.verbose:
                detail = args.get("command") or args.get("path") or args.get("pattern") or ""
                tag = f"{self.task}/{who}" if who else self.task
                print(f"  [{tag}] {self.tool_calls:>3}. {name} {str(detail)[:80]}", flush=True)

    def sub_tool_call(self, who, name, args):
        self.tool_call(name, args, who)

    def sub_tool_result(self, who, result):
        self.tool_result(result)

    def tool_result(self, result):
        if result.startswith("错误"):
            with self._lock:
                self.tool_errors += 1

    def info(self, text):
        if self.verbose:
            print(f"  [{self.task}] {text[:200]}", flush=True)

    def __getattr__(self, name):  # assistant / delta / info / warn / error 都忽略
        return lambda *a, **k: None


def list_tasks(pattern: str | None) -> list[Path]:
    tasks = sorted(p for p in TASKS_DIR.iterdir() if (p / "prompt.md").is_file())
    patterns = [p.strip() for p in (pattern or "").split(",") if p.strip()]  # 多个用逗号分隔
    return [t for t in tasks if not patterns or any(p in t.name for p in patterns)]


def task_config(task: Path) -> dict:
    """任务目录里可选的 task.json，比如大任务需要更多步数：{"max_steps": 80}；
    非 Python 任务指定判分命令：{"test_command": ["node", "--test", "{tests}/*.test.mjs"]}（{tests} 换成隐藏测试目录）。"""
    path = task / "task.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def prepare_workspace(task: Path) -> Path:
    ws = Path(tempfile.mkdtemp(prefix=f"coder-eval-{task.name}-"))
    if (task / "setup").is_dir():
        shutil.copytree(task / "setup", ws, dirs_exist_ok=True)
    return ws


def run_hidden_tests(task: Path, ws: Path) -> tuple[bool, str]:
    shutil.copytree(task / "tests", ws / TEST_DIR_NAME, dirs_exist_ok=True)
    custom = task_config(task).get("test_command")
    if custom:
        cmd = [part.replace("{tests}", TEST_DIR_NAME) for part in custom]
        cmd[0] = shutil.which(cmd[0]) or cmd[0]  # Windows 上 node 是 node.exe
    else:
        # python -m pytest 会把当前目录（工作区）加进 sys.path，测试就能 import agent 写的模块
        cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", TEST_DIR_NAME]
    try:
        proc = subprocess.run(cmd, cwd=ws, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=TEST_TIMEOUT)
    except subprocess.TimeoutExpired:
        return False, f"测试超时（{TEST_TIMEOUT} 秒）"
    return proc.returncode == 0, (proc.stdout + proc.stderr)[-3000:]


def run_task(task: Path, make_llm, args, run_dir: Path, run_index: int = 0) -> Result:
    result = Result(task=task.name)
    ws = prepare_workspace(task)
    workspace = Workspace(ws, read_guard=not args.no_read_guard)
    ui = RecordingUI(task.name, getattr(args, "verbose", False))
    perms = PermissionManager(ask=lambda *a: ("y", ""), auto=True)
    max_steps = task_config(task).get("max_steps", args.max_steps)
    context_limit = 0 if args.no_compact else args.context_limit
    sandbox = DockerSandbox(ws) if getattr(args, "sandbox", False) else None
    processes = ProcessManager(sandbox)
    if getattr(args, "team", False):
        agent = Team(make_llm, ws, perms, ui, max_steps=max_steps, context_limit=context_limit,
                     read_guard=not args.no_read_guard, delegate=args.team, processes=processes, sandbox=sandbox)
    else:
        agent = Agent(make_llm(), build_tools(workspace, processes, sandbox), workspace, perms, ui,
                      max_steps=max_steps, context_limit=context_limit, sandbox=sandbox)
    start = time.time()
    try:
        agent.run((task / "prompt.md").read_text(encoding="utf-8"))
    except Exception as e:  # API 失败等：记为失败，但仍然判分（可能已经做完了）
        result.error = f"{type(e).__name__}: {e}"
    processes.stop_all()  # agent 忘了停的后台进程（比如开发服务器）不能留到判分和下一题
    if sandbox:
        sandbox.stop()
    result.seconds = round(time.time() - start, 1)
    result.passed, result.test_output = run_hidden_tests(task, ws)
    result.steps, result.compactions = agent.steps, agent.compactions
    result.tool_calls, result.tool_errors = ui.tool_calls, ui.tool_errors
    result.llm_retries = agent.retries if isinstance(agent, Team) else getattr(agent.llm, "retries", 0)
    result.prompt_tokens = agent.usage["prompt"]
    result.completion_tokens = agent.usage["completion"]
    result.cached_tokens = agent.usage["cached"]
    # 保存完整轨迹，方便做失败分析（图片换成引用，避免文件过大）
    trajectory = {"result": asdict(result), "call_log": agent.call_log,
                  "messages": Store(run_dir / ".store").pack_messages(agent.messages)}
    if isinstance(agent, Team):
        trajectory["team"] = team_messages(agent)
    suffix = f"-{run_index + 1}" if args.repeat > 1 else ""
    (run_dir / "trajectories").mkdir(parents=True, exist_ok=True)
    (run_dir / "trajectories" / f"{task.name}{suffix}.json").write_text(
        json.dumps(trajectory, ensure_ascii=False, indent=1), encoding="utf-8")
    if args.keep:
        result.error = (result.error + f" 工作区：{ws}").strip()
    else:
        shutil.rmtree(ws, ignore_errors=True)
    return result


CATEGORIES = {"algo": "算法", "bug": "修 bug", "feature": "加功能", "refactor": "重构",
              "multi": "多文件", "debug": "调试", "long": "长任务", "large": "大任务", "js": "JavaScript"}


def token_prices() -> tuple[float, float, float] | None:
    """可选：在 .env 里配置每百万 token 的价格（未命中缓存的输入、命中缓存的输入、输出），报告里会换算成费用。"""
    try:
        return tuple(float(os.environ[k]) for k in ("CODER_PRICE_INPUT", "CODER_PRICE_CACHED", "CODER_PRICE_OUTPUT"))
    except (KeyError, ValueError):
        return None


def estimate_cost(prompt: int, cached: int, completion: int, prices) -> float:
    p_in, p_cached, p_out = prices
    return ((prompt - cached) * p_in + cached * p_cached + completion * p_out) / 1_000_000


def summarize(results: list[Result], label: str) -> str:
    n = len(results)
    passed = sum(r.passed for r in results)
    total = lambda attr, rs=results: sum(getattr(r, attr) for r in rs)
    prompt, cached, completion = total("prompt_tokens"), total("cached_tokens"), total("completion_tokens")
    by_cat: dict[str, list[Result]] = {}
    for r in results:
        by_cat.setdefault(CATEGORIES.get(r.task.split("_")[0], "其他"), []).append(r)
    lines = [
        f"## {label}",
        "",
        f"- 通过率：**{passed}/{n}（{passed / n:.0%}）**",
        "- 按类型：" + " · ".join(f"{c} {sum(r.passed for r in rs)}/{len(rs)}" for c, rs in by_cat.items()),
        f"- 平均每次运行：调用模型 {total('steps') / n:.1f} 次，工具调用 {total('tool_calls') / n:.1f} 次"
        f"（其中出错 {total('tool_errors') / n:.1f} 次），耗时 {total('seconds') / n:.0f} 秒",
        f"- token 合计：输入 {prompt:,}（命中缓存 {cached:,}，命中率 {cached / max(prompt, 1):.0%}；"
        f"**未命中 {prompt - cached:,}**），输出 {completion:,}；平均每次运行输入 {prompt / n:,.0f}、输出 {completion / n:,.0f}",
    ]
    if total("llm_retries"):
        lines.append(f"- 模型调用因网络等临时错误重试：共 {total('llm_retries')} 次")
    compacted = [r for r in results if r.compactions]
    if compacted:
        lines.append(f"- 上下文压缩：共 {total('compactions')} 次，出现在 {len(compacted)}/{n} 次运行中；"
                     f"压缩过的运行通过 {sum(r.passed for r in compacted)}/{len(compacted)}")
    prices = token_prices()
    if prices:
        lines.append(f"- 估算费用：合计 {estimate_cost(prompt, cached, completion, prices):.2f}，"
                     f"平均每次运行 {estimate_cost(prompt, cached, completion, prices) / n:.3f}")
    lines += ["", "| 任务 | 通过 | 模型调用 | 工具出错 | 输入 tokens | 缓存命中率 | 输出 tokens | 耗时 |",
              "|---|---|---|---|---|---|---|---|"]
    by_task: dict[str, list[Result]] = {}
    for r in results:
        by_task.setdefault(r.task, []).append(r)
    for task, rs in sorted(by_task.items()):
        ok, k = sum(r.passed for r in rs), len(rs)
        if k == 1:
            r = rs[0]
            mark = "✅" if r.passed else ("⚠️ 异常" if r.error and "工作区" not in r.error else "❌")
        else:
            mark = "✅" if ok == k else "❌" if ok == 0 else f"{ok}/{k}"
        p, c = total("prompt_tokens", rs) / k, total("cached_tokens", rs) / k
        lines.append(f"| {task} | {mark} | {total('steps', rs) / k:.0f} | {total('tool_errors', rs) / k:.0f} | "
                     f"{p:,.0f} | {c / max(p, 1):.0%} | {total('completion_tokens', rs) / k:,.0f} | "
                     f"{total('seconds', rs) / k:.0f}s |")
    if any(len(rs) > 1 for rs in by_task.values()):
        lines.append("\n每个任务的数字是多次运行的平均值。")
    return "\n".join(lines)


def validate(tasks: list[Path]) -> bool:
    """校验评测集：初始代码不应通过测试，参考答案必须通过。"""
    ok = True
    for task in tasks:
        ws = prepare_workspace(task)
        before, _ = run_hidden_tests(task, ws)
        if (task / "solution").is_dir():
            shutil.copytree(task / "solution", ws, dirs_exist_ok=True)
        after, output = run_hidden_tests(task, ws)
        shutil.rmtree(ws, ignore_errors=True)
        good = not before and after
        ok &= good
        print(f"{'✓' if good else '✗'} {task.name}：初始代码{'通过（错误！）' if before else '不通过'}，"
              f"参考答案{'通过' if after else '不通过（错误！）'}")
        if not after:
            print(output)
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(description="coder 评测")
    parser.add_argument("--tasks", help="只运行名字包含这些字符串的任务，多个用逗号分隔")
    parser.add_argument("--repeat", type=int, default=1, help="每个任务运行几次")
    parser.add_argument("--jobs", type=int, default=4, help="并行运行的任务数")
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument("--model", help="覆盖 .env 里的模型")
    parser.add_argument("--context-limit", type=int, help="上下文压缩阈值（token）")
    parser.add_argument("--no-read-guard", action="store_true", help="消融：关闭“先读后改”")
    parser.add_argument("--no-compact", action="store_true", help="消融：关闭上下文压缩")
    parser.add_argument("--team", nargs="?", const="auto", choices=["auto", "always"],
                        help="团队模式：主 agent 拆分任务派给子 agent。auto 由主 agent 判断是否拆分，always 必须拆分")
    parser.add_argument("--keep", action="store_true", help="保留每个任务的工作区，方便查看")
    parser.add_argument("--sandbox", action="store_true", help="agent 的命令在 Docker 沙箱里执行（隐藏测试仍在本机运行）")
    parser.add_argument("--verbose", action="store_true", help="实时打印每个任务的每一步工具调用")
    parser.add_argument("--validate", action="store_true", help="不调用模型，用参考答案校验评测集")
    args = parser.parse_args()
    use_utf8_output()

    tasks = list_tasks(args.tasks)
    if not tasks:
        sys.exit("没有找到任务")
    if args.validate:
        sys.exit(0 if validate(tasks) else 1)

    cfg = Config.from_env()
    if args.model:
        cfg.model = args.model
    if not cfg.api_key:
        sys.exit("未找到 CODER_API_KEY")
    args.context_limit = args.context_limit or cfg.context_limit
    from .llm import LLM

    variant = "".join([f" team-{args.team}" if args.team else "", " -read-guard" if args.no_read_guard else "", " -compact" if args.no_compact else "",
                       f" ctx{args.context_limit}" if args.context_limit != cfg.context_limit and not args.no_compact else ""])
    label = f"{cfg.model}{variant} · coder v{__version__} · {datetime.now():%Y-%m-%d %H:%M}"
    run_dir = RESULTS_DIR / f"{datetime.now():%Y%m%d-%H%M%S}-{cfg.model}{variant.replace(' ', '')}"
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"评测：{len(tasks)} 个任务 × {args.repeat} 次 · {label}\n")

    jobs = [(t, i) for i in range(args.repeat) for t in tasks]
    lock = threading.Lock()

    def work(job):
        task, i = job
        r = run_task(task, lambda: LLM(cfg), args, run_dir, i)
        with lock:
            print(f"{'✓' if r.passed else '✗'} {r.task:<22} 模型调用 {r.steps:>2}  工具 {r.tool_calls:>2}  "
                  f"tokens {r.prompt_tokens + r.completion_tokens:>7,}  压缩 {r.compactions}  {r.seconds:>5.0f}s  {r.error}")
        return r

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(work, jobs))

    report = summarize(results, label)
    (run_dir / "summary.md").write_text(report + "\n", encoding="utf-8")
    (run_dir / "results.json").write_text(
        json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n" + report)
    print(f"\n结果和每个任务的完整轨迹保存在：{run_dir}")


if __name__ == "__main__":
    main()
