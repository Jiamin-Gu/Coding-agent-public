"""命令行接口测试（通过 ``python -m ledger`` 子进程）。"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args, cwd=ROOT):
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "ledger", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )


def test_add_list_delete_flow(tmp_path):
    db = tmp_path / "ledger.json"

    result = run("--file", str(db), "add", "expense", "12.50", "餐饮", "2026-01-05", "--note", "午饭")
    assert result.returncode == 0
    assert result.stdout.strip() == "已添加 #1"

    result = run("--file", str(db), "add", "income", "100", "工资", "2026-01-01")
    assert result.stdout.strip() == "已添加 #2"

    result = run("--file", str(db), "list")
    assert result.returncode == 0
    assert result.stdout == (
        "#2 2026-01-01 income 工资 100.00\n"
        "#1 2026-01-05 expense 餐饮 12.50 午饭\n"
    )

    result = run("--file", str(db), "delete", "1")
    assert result.returncode == 0
    assert result.stdout.strip() == "已删除 #1"


def test_list_empty(tmp_path):
    db = tmp_path / "ledger.json"
    result = run("--file", str(db), "list")
    assert result.returncode == 0
    assert result.stdout.strip() == "（无记录）"


def test_list_filters(tmp_path):
    db = tmp_path / "ledger.json"
    run("--file", str(db), "add", "expense", "5", "交通", "2026-01-10")
    run("--file", str(db), "add", "income", "100", "工资", "2026-01-05")

    result = run("--file", str(db), "list", "--kind", "income")
    assert result.stdout == "#2 2026-01-05 income 工资 100.00\n"

    result = run("--file", str(db), "list", "--from", "2026-01-08")
    assert result.stdout == "#1 2026-01-10 expense 交通 5.00\n"


def test_balance(tmp_path):
    db = tmp_path / "ledger.json"
    run("--file", str(db), "add", "income", "100", "工资", "2026-01-05")
    run("--file", str(db), "add", "expense", "112.50", "餐饮", "2026-01-06")

    result = run("--file", str(db), "balance")
    assert result.returncode == 0
    assert result.stdout.strip() == "-12.50"


def test_report(tmp_path):
    db = tmp_path / "ledger.json"
    run("--file", str(db), "add", "income", "1000", "工资", "2026-03-01")
    run("--file", str(db), "add", "expense", "12.50", "餐饮", "2026-03-05")
    run("--file", str(db), "add", "expense", "30", "餐饮", "2026-03-10")
    run("--file", str(db), "add", "expense", "8", "交通", "2026-03-11")

    result = run("--file", str(db), "report", "2026", "3")
    assert result.returncode == 0
    assert result.stdout == (
        "收入 1000.00 支出 50.50 结余 949.50\n"
        "餐饮 42.50\n"
        "交通 8.00\n"
    )


def test_budget_set_and_status(tmp_path):
    db = tmp_path / "ledger.json"

    result = run("--file", str(db), "budget", "set", "餐饮", "100")
    assert result.returncode == 0
    assert result.stdout.strip() == "已设置预算 餐饮 100.00"

    run("--file", str(db), "add", "expense", "120", "餐饮", "2026-03-05")

    result = run("--file", str(db), "budget", "status", "2026", "3")
    assert result.returncode == 0
    assert result.stdout == "餐饮 已用 120.00 / 预算 100.00 超支\n"


def test_export_import(tmp_path):
    db = tmp_path / "ledger.json"
    run("--file", str(db), "add", "expense", "12.50", "餐饮", "2026-01-05", "--note", "午饭")
    run("--file", str(db), "add", "income", "100", "工资", "2026-01-01")

    csv_path = tmp_path / "out.csv"
    result = run("--file", str(db), "export", str(csv_path))
    assert result.returncode == 0
    assert result.stdout.strip() == "已导出 2 条"

    db2 = tmp_path / "ledger2.json"
    result = run("--file", str(db2), "import", str(csv_path))
    assert result.returncode == 0
    assert result.stdout.strip() == "已导入 2 条"

    result = run("--file", str(db2), "list")
    assert result.stdout == (
        "#1 2026-01-01 income 工资 100.00\n"
        "#2 2026-01-05 expense 餐饮 12.50 午饭\n"
    )


def test_error_missing_record(tmp_path):
    db = tmp_path / "ledger.json"
    result = run("--file", str(db), "delete", "1")
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.startswith("错误：")
    assert "#1" in result.stderr


def test_error_invalid_amount(tmp_path):
    db = tmp_path / "ledger.json"
    result = run("--file", str(db), "add", "expense", "abc", "餐饮", "2026-01-05")
    assert result.returncode == 1
    assert result.stderr.startswith("错误：")


def test_error_invalid_date(tmp_path):
    db = tmp_path / "ledger.json"
    result = run("--file", str(db), "add", "expense", "1", "餐饮", "2026-13-40")
    assert result.returncode == 1
    assert result.stderr.startswith("错误：")


def test_error_bad_import(tmp_path):
    db = tmp_path / "ledger.json"
    bad = tmp_path / "bad.csv"
    bad.write_text(
        "date,kind,category,amount,note\n"
        "2026-01-05,expense,餐饮,-5,x\n",
        encoding="utf-8",
    )
    result = run("--file", str(db), "import", str(bad))
    assert result.returncode == 1
    assert result.stderr.startswith("错误：")
    assert "2" in result.stderr
