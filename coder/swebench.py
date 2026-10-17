"""SWE-bench Lite 子集评测：在真实开源项目的真实 issue 上检验 agent。

自己写的评测任务规格清楚、都是 Python，外部的公认题目更能说明问题。SWE-bench 的每道题是某个开源项目里一个
真实的 issue：从当时的代码开始，agent 只看到 issue 描述，修完以后套上官方的测试补丁判分：
FAIL_TO_PASS（修之前失败、修好后应该通过）和 PASS_TO_PASS（原来就通过、不能被改坏）全部通过才算解决。

为了能在普通电脑上跑，只选了依赖轻、测试不需要联网的项目（pytest、flask），环境在 Docker 沙箱里搭建：
- 仓库克隆一次缓存起来，每道题从缓存复制一份工作区，签出到出题时的提交
- 每个"项目 + 版本"一个虚拟环境（uv 安装对应的 Python 版本），放在沙箱的持久卷里，第一次需要联网，之后复用
- agent 在沙箱里工作，不能联网；测试补丁在它做完之后才放进工作区

    python -m coder.swebench fetch               # 下载选定的题目（instances.json）
    python -m coder.swebench validate            # 用官方答案校验环境：不打补丁 FAIL_TO_PASS 失败，打了全部通过
    python -m coder.swebench run --model kimi-k2.7-code
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from . import __version__, use_utf8_output
from .agent import Agent
from .config import Config
from .eval import RESULTS_DIR, RecordingUI, Result, summarize
from .permissions import PermissionManager
from .sandbox import DockerSandbox, docker_status
from .store import Store
from .tools import ProcessManager, build_tools
from .workspace import Workspace

ROOT = Path(__file__).resolve().parent.parent / "evals" / "swebench"
INSTANCES_FILE = ROOT / "instances.json"
CACHE = Path(os.getenv("CODER_SWEBENCH_CACHE") or ROOT / "cache")  # 仓库缓存和工作区，体积较大，放在项目所在的盘
DATASET_ROWS = ("https://datasets-server.huggingface.co/rows?dataset=princeton-nlp/SWE-bench_Lite"
                "&config=default&split=test&offset={offset}&length=100")

# 选定的题目：依赖轻、测试不需要联网
SELECTED = [
    "pytest-dev__pytest-7373", "pytest-dev__pytest-7432", "pytest-dev__pytest-7490", "pytest-dev__pytest-8365",
    "pytest-dev__pytest-8906", "pytest-dev__pytest-9359", "pytest-dev__pytest-11143", "pytest-dev__pytest-11148",
    "pallets__flask-4992", "pallets__flask-5063",
]

# 每个"项目 + 版本"的环境，参考 SWE-bench 官方评测工具的设置
PYTEST_COMMON = ["attrs==23.1.0", "iniconfig==2.0.0", "packaging==23.1", "py==1.11.0", "tomli==2.0.1",
                 "hypothesis==6.82.0", "xmlschema==2.4.0", "pygments==2.16.1", "nose==1.3.7", "mock==5.1.0",
                 "requests==2.31.0"]
SPECS = {
    ("pytest-dev/pytest", "5.4"): {"python": "3.9", "packages": PYTEST_COMMON + ["pluggy==0.13.1", "more-itertools==8.12.0",
                                                                                 "wcwidth==0.2.6", "toml==0.10.2"]},
    ("pytest-dev/pytest", "6.0"): {"python": "3.9", "packages": PYTEST_COMMON + ["pluggy==0.13.1", "more-itertools==8.12.0",
                                                                                 "toml==0.10.2"]},
    ("pytest-dev/pytest", "6.3"): {"python": "3.9", "packages": PYTEST_COMMON + ["pluggy==0.13.1", "toml==0.10.2"]},
    ("pytest-dev/pytest", "7.0"): {"python": "3.9", "packages": PYTEST_COMMON + ["pluggy==0.13.1"]},
    ("pytest-dev/pytest", "8.0"): {"python": "3.9", "packages": PYTEST_COMMON + ["pluggy==1.3.0", "exceptiongroup==1.1.3"]},
    ("pallets/flask", "2.3"): {"python": "3.11", "packages": ["pytest==7.4.0", "click==8.1.3", "itsdangerous==2.1.2",
                                                              "Jinja2==3.1.2", "MarkupSafe==2.1.1", "Werkzeug==2.3.7",
                                                              "blinker==1.6.2", "python-dotenv==1.0.0"]},
}

PROMPT = """The source code of the {repo} repository is in the current directory, with a development environment \
already installed (run tests with `python -m pytest`). Resolve the following GitHub issue by changing the \
library's source code. Do not modify existing tests; you may add new tests to check your fix. The environment has \
no network access.

<issue>
{problem}
</issue>"""


# ---------- 题目 ----------

def fetch() -> int:
    """从 Hugging Face 下载 SWE-bench Lite，只保存选定的题目。"""
    wanted, rows = set(SELECTED), []
    for offset in (0, 100, 200):
        with urllib.request.urlopen(DATASET_ROWS.format(offset=offset), timeout=60) as r:
            rows += [x["row"] for x in json.load(r)["rows"]]
    chosen = [r for r in rows if r["instance_id"] in wanted]
    ROOT.mkdir(parents=True, exist_ok=True)
    keep = ("instance_id", "repo", "base_commit", "version", "problem_statement", "patch", "test_patch",
            "FAIL_TO_PASS", "PASS_TO_PASS", "created_at")
    INSTANCES_FILE.write_text(json.dumps([{k: r[k] for k in keep} for r in chosen], ensure_ascii=False, indent=1),
                              encoding="utf-8")
    print(f"已保存 {len(chosen)} 道题到 {INSTANCES_FILE}")
    return 0 if len(chosen) == len(wanted) else 1


def load_instances(pattern: str | None = None) -> list[dict]:
    if not INSTANCES_FILE.is_file():
        sys.exit("还没有题目：先运行 python -m coder.swebench fetch")
    items = json.loads(INSTANCES_FILE.read_text(encoding="utf-8"))
    if pattern:
        keys = pattern.split(",")
        items = [i for i in items if any(k in i["instance_id"] for k in keys)]
    return items


# ---------- 工作区和环境 ----------

def git(*args, cwd=None, check=True) -> subprocess.CompletedProcess:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:3])} 失败：{r.stderr.strip()[:500]}")
    return r


def prepare_workspace(inst: dict) -> Path:
    """仓库克隆一次缓存；每道题从缓存复制一份（本地克隆，硬链接对象，很快），签出到出题时的提交。"""
    repo_dir = CACHE / "repos" / inst["repo"].replace("/", "__")
    if not repo_dir.is_dir():
        repo_dir.parent.mkdir(parents=True, exist_ok=True)
        print(f"克隆 {inst['repo']}（只需一次）……", flush=True)
        git("clone", "-q", f"https://github.com/{inst['repo']}.git", str(repo_dir))
    ws = CACHE / "work" / f"{inst['instance_id']}-{uuid.uuid4().hex[:8]}"  # 多个评测同时跑，名字不能重复
    ws.parent.mkdir(parents=True, exist_ok=True)
    git("clone", "-q", str(repo_dir), str(ws))
    git("checkout", "-q", inst["base_commit"], cwd=ws)
    return ws


def remove_tree(path: Path) -> None:
    """删除工作区。Windows 上 git 的对象文件是只读的，shutil.rmtree 删不掉，先去掉只读属性再删。"""
    def retry(func, target, _exc):
        os.chmod(target, stat.S_IWRITE)
        func(target)
    shutil.rmtree(path, onerror=retry)


def env_key(inst: dict) -> str:
    spec = SPECS[(inst["repo"], inst["version"])]
    digest = hashlib.sha1(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:8]
    return f"{inst['repo'].split('/')[1]}-{inst['version']}-{digest}"


def venv_path(inst: dict) -> str:
    return f"/home/coder/venvs/{env_key(inst)}"


def make_sandbox(inst: dict, ws: Path) -> DockerSandbox:
    venv = venv_path(inst)
    path = f"{venv}/bin:/home/coder/.local/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin"
    # setuptools_scm 按 git 标签算版本号，本地克隆不一定有合适的标签，直接给一个
    return DockerSandbox(ws, env={"PATH": path, "VIRTUAL_ENV": venv,
                                  "SETUPTOOLS_SCM_PRETEND_VERSION": f"{inst['version']}.0"})


def sh(sandbox: DockerSandbox, command: str, network: bool = False, timeout: int = 900) -> tuple[int, str]:
    proc = sandbox.popen(command, network=network)
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        sandbox.kill(proc)
        return 124, "超时"
    finally:
        sandbox.finished(proc)
    return proc.returncode, out.decode("utf-8", errors="replace")


def setup_env(inst: dict, sandbox: DockerSandbox) -> None:
    """在沙箱里准备这道题的环境：对应版本的 Python 虚拟环境 + 固定版本的依赖 + 可编辑安装当前仓库。"""
    spec = SPECS[(inst["repo"], inst["version"])]
    venv = venv_path(inst)
    packages = " ".join(f"'{p}'" for p in spec["packages"])
    script = (
        "set -e; command -v uv >/dev/null || pip install --user -q uv; "
        f"[ -x {venv}/bin/python ] || uv venv -q --python {spec['python']} {venv}; "
        f"uv pip install -q --python {venv}/bin/python {packages} 'setuptools<70' wheel; "
        f"uv pip install -q --python {venv}/bin/python --no-deps -e . "
    )
    code, out = sh(sandbox, script, network=True)
    if code != 0:
        raise RuntimeError(f"环境准备失败：{out[-1500:]}")


# ---------- 判分 ----------

def test_files(test_patch: str) -> list[str]:
    return re.findall(r"^diff --git a/(\S+) b/", test_patch, re.M)


def apply_patch(ws: Path, patch: str, name: str) -> None:
    path = ws / f".{name}.patch"
    path.write_text(patch, encoding="utf-8", newline="\n")
    try:
        git("apply", "--whitespace=nowarn", str(path), cwd=ws)
    finally:
        path.unlink(missing_ok=True)


PASSED = re.compile(r"^(PASSED|XFAIL|XPASS)\s+(\S+)", re.M)
FAILED = re.compile(r"^(FAILED|ERROR)\s+(\S+)", re.M)


def run_tests(inst: dict, ws: Path, sandbox: DockerSandbox) -> tuple[bool, str, dict]:
    """恢复测试文件、套上官方测试补丁，运行相关测试。返回 (是否解决, 输出摘要, 明细)。"""
    files = test_files(inst["test_patch"])
    existing = [f for f in files if git("cat-file", "-e", f"{inst['base_commit']}:{f}", cwd=ws, check=False).returncode == 0]
    if existing:  # agent 可能改过测试文件，先恢复成出题时的样子
        git("checkout", "-q", inst["base_commit"], "--", *existing, cwd=ws)
    for f in set(files) - set(existing):  # 补丁要新建的文件，agent 可能自己建过同名的（比如测试数据），先删掉
        (ws / f).unlink(missing_ok=True)
    apply_patch(ws, inst["test_patch"], "test")
    tests = [f for f in files if f.endswith(".py")]  # 测试补丁里也可能有数据文件（比如 config.toml）
    code, out = sh(sandbox, "python -m pytest -rA -p no:cacheprovider -W ignore::DeprecationWarning "
                            + " ".join(tests), timeout=900)
    passed = {m.group(2) for m in PASSED.finditer(out)}
    failed = {m.group(2) for m in FAILED.finditer(out)}
    f2p, p2p = json.loads(inst["FAIL_TO_PASS"]), json.loads(inst["PASS_TO_PASS"])

    def ok(test: str) -> bool:
        return test in passed and test not in failed

    detail = {"FAIL_TO_PASS": {t: ok(t) for t in f2p}, "PASS_TO_PASS_failed": [t for t in p2p if not ok(t)]}
    solved = all(detail["FAIL_TO_PASS"].values()) and not detail["PASS_TO_PASS_failed"]
    summary = (f"FAIL_TO_PASS {sum(detail['FAIL_TO_PASS'].values())}/{len(f2p)}，"
               f"PASS_TO_PASS {len(p2p) - len(detail['PASS_TO_PASS_failed'])}/{len(p2p)}")
    return solved, summary + "\n" + out[-3000:], detail


# ---------- 运行 ----------

def deny_network(tool, preview, **kw):
    if kw.get("network"):
        return "n", "评测环境不能联网，依赖已经装好了"
    return "y", ""


def run_instance(inst: dict, make_llm, args, run_dir: Path) -> Result:
    result = Result(task=inst["instance_id"])
    ui = RecordingUI(inst["instance_id"], getattr(args, "verbose", False))
    agent, ws, sandbox = None, None, None
    try:
        ws = prepare_workspace(inst)
        sandbox = make_sandbox(inst, ws)
        setup_env(inst, sandbox)
        workspace = Workspace(ws)
        agent = Agent(make_llm(), build_tools(workspace, ProcessManager(sandbox), sandbox), workspace,
                      PermissionManager(ask=deny_network, auto=True), ui, max_steps=args.max_steps,
                      context_limit=args.context_limit, sandbox=sandbox)
        start = time.time()
        try:
            agent.run(PROMPT.format(repo=inst["repo"], problem=inst["problem_statement"]))
        except Exception as e:
            result.error = f"{type(e).__name__}: {e}"
        result.seconds = round(time.time() - start, 1)
        model_patch = git("diff", cwd=ws).stdout
        result.passed, result.test_output, detail = run_tests(inst, ws, sandbox)
    except Exception as e:  # 环境问题：记下来，不算模型的分
        result.error = f"{type(e).__name__}: {e}"
        model_patch, detail = "", {}
    finally:
        if sandbox:
            sandbox.stop()
    if agent:
        result.steps, result.compactions = agent.steps, agent.compactions
        result.tool_calls, result.tool_errors = ui.tool_calls, ui.tool_errors
        result.prompt_tokens, result.completion_tokens = agent.usage["prompt"], agent.usage["completion"]
        result.cached_tokens = agent.usage["cached"]
        result.llm_retries = getattr(agent.llm, "retries", 0)
    (run_dir / "trajectories").mkdir(parents=True, exist_ok=True)
    (run_dir / "trajectories" / f"{inst['instance_id']}.json").write_text(json.dumps(
        {"result": asdict(result), "model_patch": model_patch, "tests": detail,
         "messages": Store(run_dir / ".store").pack_messages(agent.messages) if agent else []},
        ensure_ascii=False, indent=1), encoding="utf-8")
    if ws and not args.keep:
        remove_tree(ws)
    return result


def validate(instances: list[dict]) -> bool:
    """校验环境：不打补丁时 FAIL_TO_PASS 不能全过，打上官方答案后必须全部通过。"""
    all_ok = True
    for inst in instances:
        ws = prepare_workspace(inst)
        sandbox = make_sandbox(inst, ws)
        try:
            setup_env(inst, sandbox)
            before, _, detail_before = run_tests(inst, ws, sandbox)
            git("checkout", "-q", "--", ".", cwd=ws)
            git("clean", "-q", "-fd", cwd=ws)
            apply_patch(ws, inst["patch"], "gold")
            after, out, detail = run_tests(inst, ws, sandbox)
            ok = not before and after
            note = "" if ok else ("（不打补丁也通过）" if before else f"\n    {out.splitlines()[0]}；"
                                  f"没通过的 PASS_TO_PASS：{detail.get('PASS_TO_PASS_failed', [])[:5]}")
        except Exception as e:
            ok, note = False, f"：{e}"
        finally:
            sandbox.stop()
            remove_tree(ws)
        all_ok &= ok
        print(f"{'✓' if ok else '✗'} {inst['instance_id']}{note}", flush=True)
    return all_ok


def export(run_dirs: list[Path], out: Path) -> None:
    """把评测里 agent 交出的补丁整理成示例：每道题一个目录（README + 各模型的补丁），外加总表。"""
    instances = {i["instance_id"]: i for i in load_instances()}
    table: dict[str, dict[str, str]] = {}
    models = []
    for run_dir in run_dirs:
        model = run_dir.name.split("-swebench-", 1)[-1]
        if model not in models:  # 同一个模型可能分几次跑完，合并成一列（后面的运行覆盖前面的）
            models.append(model)
        for f in sorted((run_dir / "trajectories").glob("*.json")):
            t = json.loads(f.read_text(encoding="utf-8"))
            iid, r = f.stem, t["result"]
            if ("UsageLimit" in r.get("error", "") and not r["passed"]) or "already exists in working" in r.get("error", ""):
                continue  # 被服务商的额度限流打断、或评测框架当时的问题（已修复），不算模型的成绩
            table.setdefault(iid, {})[model] = "✅" if r["passed"] else "❌"
            d = out / iid
            d.mkdir(parents=True, exist_ok=True)
            if t.get("model_patch"):
                (d / f"{model}.diff").write_text(t["model_patch"], encoding="utf-8", newline="\n")
            inst = instances[iid]
            title = inst["problem_statement"].strip().splitlines()[0][:120]
            readme = d / "README.md"
            head = (f"# {iid}\n\n**Issue**：{title}\n\n仓库 `{inst['repo']}`，版本 {inst['version']}，提交 `{inst['base_commit'][:10]}`\n\n"
                    "官方答案见 SWE-bench Lite 数据集。下面是各模型驱动 coder 交出的补丁和判分结果"
                    "（FAIL_TO_PASS：修之前失败、应该修好的测试；PASS_TO_PASS：原来就通过、不能改坏的测试）。\n\n"
                    "| 模型 | 结果 | 判分 | 调用次数 | tokens | 补丁 |\n|---|---|---|---|---|---|\n")
            rows = readme.read_text(encoding="utf-8").split("|---|---|---|---|---|---|\n", 1)[1] if readme.is_file() else ""
            line = (f"| {model} | {'✅' if r['passed'] else '❌'} | {(r['test_output'] or '').splitlines()[0] if r['test_output'] else r['error'][:60]} "
                    f"| {r['steps']} | {r['prompt_tokens'] + r['completion_tokens']:,} | "
                    + (f"[{model}.diff]({model}.diff)" if t.get("model_patch") else "（没有修改）") + " |\n")
            rows = "".join(l + "\n" for l in rows.splitlines() if l and not l.startswith(f"| {model} |")) + line
            readme.write_text(head + rows, encoding="utf-8")
    lines = ["# SWE-bench Lite 子集", "",
             "10 道来自 pytest、flask 的真实 issue（依赖轻、测试不需要联网），环境在 Docker 沙箱里搭建，"
             "agent 只看到 issue 描述，修完后套上官方测试补丁判分。每道题的目录里有各模型交出的补丁。", "",
             "| 题目 | " + " | ".join(models) + " |", "|---|" + "---|" * len(models)]
    for iid in sorted(table):
        lines.append(f"| [{iid}]({iid}/README.md) | " + " | ".join(table[iid].get(m, "—") for m in models) + " |")
    lines.append("| **解决 / 已跑** | " + " | ".join(
        f"**{sum(1 for v in table.values() if v.get(m) == '✅')}/{sum(1 for v in table.values() if m in v)}**"
        for m in models) + " |")
    lines += ["", "“—”表示这道题还没有这个模型的有效结果（没跑到，或者运行被服务商的额度限流打断）。"]
    (out / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"已导出到 {out}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m coder.swebench", description="SWE-bench Lite 子集评测")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch", help="下载选定的题目")
    v = sub.add_parser("validate", help="用官方答案校验环境")
    v.add_argument("--instances", help="只运行名字包含这些字符串的题目，逗号分隔")
    r = sub.add_parser("run", help="运行评测")
    r.add_argument("--instances")
    r.add_argument("--model")
    r.add_argument("--jobs", type=int, default=2)
    r.add_argument("--max-steps", type=int, default=60)
    r.add_argument("--keep", action="store_true", help="保留工作区")
    r.add_argument("--verbose", action="store_true")
    e = sub.add_parser("export", help="把评测结果整理成示例")
    e.add_argument("runs", nargs="+", help="evals/results 下的评测目录")
    e.add_argument("--out", default="examples/swebench")
    args = parser.parse_args()
    use_utf8_output()

    if args.cmd == "fetch":
        sys.exit(fetch())
    if args.cmd == "export":
        return export([Path(p) for p in args.runs], Path(args.out))
    ok, why = docker_status()
    if not ok:
        sys.exit(f"SWE-bench 评测需要 Docker 沙箱：{why}")
    instances = load_instances(args.instances)
    if args.cmd == "validate":
        sys.exit(0 if validate(instances) else 1)

    cfg = Config.from_env()
    if args.model:
        cfg.model = args.model
    if not cfg.api_key:
        sys.exit("未找到 CODER_API_KEY")
    args.context_limit = cfg.context_limit
    from .llm import LLM
    label = f"{cfg.model} · SWE-bench Lite 子集 · coder v{__version__} · {datetime.now():%Y-%m-%d %H:%M}"
    run_dir = RESULTS_DIR / f"{datetime.now():%Y%m%d-%H%M%S}-swebench-{cfg.model}"
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"SWE-bench Lite 子集：{len(instances)} 道题 · {label}\n", flush=True)
    lock = threading.Lock()

    def work(inst):
        res = run_instance(inst, lambda: LLM(cfg), args, run_dir)
        with lock:
            print(f"{'✓' if res.passed else '✗'} {res.task:<28} 模型调用 {res.steps:>2}  工具 {res.tool_calls:>2}  "
                  f"tokens {res.prompt_tokens + res.completion_tokens:>8,}  {res.seconds:>5.0f}s  "
                  f"{res.test_output.splitlines()[0] if res.test_output else ''}  {res.error}", flush=True)
        return res

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(work, instances))
    report = summarize(results, label)
    (run_dir / "summary.md").write_text(report + "\n", encoding="utf-8")
    (run_dir / "results.json").write_text(json.dumps([asdict(x) for x in results], ensure_ascii=False, indent=1),
                                          encoding="utf-8")
    print("\n" + report + f"\n\n结果保存在：{run_dir}")


if __name__ == "__main__":
    main()
