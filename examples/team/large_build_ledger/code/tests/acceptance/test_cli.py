"""Acceptance tests for the command line interface.

Run as ``python -m ledger [--file PATH] subcommand ...`` from the project root.
These tests encode the requirements in docs/PRD.md and must not be modified by
the implementation tasks.
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run(*args, cwd=ROOT):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "ledger", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(cwd),
        env=env,
    )


def test_cli_add_and_list(tmp_path):
    f = tmp_path / "d.json"
    r = run("--file", str(f), "add", "expense", "12.50", "餐饮", "2026-01-05", "--note", "午饭")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "已添加 #1"

    r = run("--file", str(f), "add", "income", "100.00", "工资", "2026-01-01")
    assert r.stdout.strip() == "已添加 #2"

    r = run("--file", str(f), "list")
    assert r.returncode == 0
    assert r.stdout.rstrip("\n").split("\n") == [
        "#2 2026-01-01 income 工资 100.00",
        "#1 2026-01-05 expense 餐饮 12.50 午饭",
    ]


def test_cli_list_empty(tmp_path):
    f = tmp_path / "d.json"
    r = run("--file", str(f), "list")
    assert r.returncode == 0
    assert r.stdout.strip() == "（无记录）"


def test_cli_list_filters(tmp_path):
    f = tmp_path / "d.json"
    run("--file", str(f), "add", "expense", "1.00", "餐饮", "2026-01-05")
    run("--file", str(f), "add", "income", "2.00", "工资", "2026-01-06")
    r = run("--file", str(f), "list", "--kind", "income")
    assert r.stdout.rstrip("\n") == "#2 2026-01-06 income 工资 2.00"
    r = run("--file", str(f), "list", "--from", "2026-01-06")
    assert r.stdout.rstrip("\n") == "#2 2026-01-06 income 工资 2.00"


def test_cli_delete_and_errors(tmp_path):
    f = tmp_path / "d.json"
    run("--file", str(f), "add", "expense", "1.00", "餐饮", "2026-01-05")
    r = run("--file", str(f), "delete", "1")
    assert r.returncode == 0
    assert r.stdout.strip() == "已删除 #1"
    r = run("--file", str(f), "delete", "1")
    assert r.returncode == 1
    assert r.stdout == ""
    assert r.stderr.startswith("错误：")


def test_cli_balance(tmp_path):
    f = tmp_path / "d.json"
    run("--file", str(f), "add", "expense", "12.50", "餐饮", "2026-01-05")
    r = run("--file", str(f), "balance")
    assert r.returncode == 0
    assert r.stdout.strip() == "-12.50"


def test_cli_report(tmp_path):
    f = tmp_path / "d.json"
    run("--file", str(f), "add", "income", "100.00", "工资", "2026-01-05")
    run("--file", str(f), "add", "expense", "30.00", "餐饮", "2026-01-06")
    run("--file", str(f), "add", "expense", "20.00", "交通", "2026-01-07")
    r = run("--file", str(f), "report", "2026", "1")
    assert r.returncode == 0
    assert r.stdout.rstrip("\n").split("\n") == [
        "收入 100.00 支出 50.00 结余 50.00",
        "餐饮 30.00",
        "交通 20.00",
    ]


def test_cli_budget_set_and_status(tmp_path):
    f = tmp_path / "d.json"
    r = run("--file", str(f), "budget", "set", "餐饮", "50.00")
    assert r.returncode == 0
    assert r.stdout.strip() == "已设置预算 餐饮 50.00"
    run("--file", str(f), "add", "expense", "30.00", "餐饮", "2026-01-06")
    r = run("--file", str(f), "budget", "status", "2026", "1")
    assert r.stdout.strip() == "餐饮 已用 30.00 / 预算 50.00"


def test_cli_budget_over(tmp_path):
    f = tmp_path / "d.json"
    run("--file", str(f), "budget", "set", "餐饮", "20.00")
    run("--file", str(f), "add", "expense", "30.00", "餐饮", "2026-01-06")
    r = run("--file", str(f), "budget", "status", "2026", "1")
    assert r.stdout.strip() == "餐饮 已用 30.00 / 预算 20.00 超支"


def test_cli_export(tmp_path):
    f = tmp_path / "d.json"
    out = tmp_path / "o.csv"
    run("--file", str(f), "add", "expense", "12.50", "餐饮", "2026-01-05", "--note", "午饭")
    r = run("--file", str(f), "export", str(out))
    assert r.returncode == 0
    assert r.stdout.strip() == "已导出 1 条"


def test_cli_import(tmp_path):
    f = tmp_path / "d.json"
    src = tmp_path / "i.csv"
    src.write_text("date,kind,category,amount,note\n2026-01-05,expense,餐饮,12.50,午饭\n", encoding="utf-8")
    r = run("--file", str(f), "import", str(src))
    assert r.returncode == 0
    assert r.stdout.strip() == "已导入 1 条"


def test_cli_import_error_line_number(tmp_path):
    f = tmp_path / "d.json"
    src = tmp_path / "i.csv"
    src.write_text(
        "date,kind,category,amount,note\n"
        "2026-01-05,expense,餐饮,12.50,\n"
        "baddate,expense,餐饮,1.00,\n",
        encoding="utf-8",
    )
    r = run("--file", str(f), "import", str(src))
    assert r.returncode == 1
    assert r.stdout == ""
    assert "3" in r.stderr
    assert r.stderr.startswith("错误：")


def test_cli_invalid_add(tmp_path):
    f = tmp_path / "d.json"
    r = run("--file", str(f), "add", "expense", "-1", "餐饮", "2026-01-05")
    assert r.returncode == 1
    assert r.stdout == ""
    assert r.stderr.startswith("错误：")


def test_cli_default_file(tmp_path):
    r = run("add", "expense", "1.00", "餐饮", "2026-01-05", cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "ledger.json").exists()
