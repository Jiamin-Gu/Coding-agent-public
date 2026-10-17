import json
import os
import subprocess
import sys

# 统一用 UTF-8 输出（Windows 下管道默认是 GBK，这不是本任务要考察的内容）
ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONPATH": os.getcwd()}


def run(tmp_path, *args):
    p = subprocess.run([sys.executable, "-m", "ledger", "--file", str(tmp_path / "d.json"), *args],
                       capture_output=True, text=True, encoding="utf-8", env=ENV)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def test_add_list_delete(tmp_path):
    assert run(tmp_path, "add", "expense", "12.5", "餐饮", "2026-01-05", "--note", "午饭") == (0, "已添加 #1", "")
    assert run(tmp_path, "add", "income", "100", "工资", "2026-01-01")[1] == "已添加 #2"
    code, out, _ = run(tmp_path, "list")
    assert code == 0 and out.splitlines() == ["#2 2026-01-01 income 工资 100.00", "#1 2026-01-05 expense 餐饮 12.50 午饭"]
    assert run(tmp_path, "list", "--kind", "expense", "--from", "2026-01-02")[1] == "#1 2026-01-05 expense 餐饮 12.50 午饭"
    assert run(tmp_path, "delete", "1")[1] == "已删除 #1"
    assert run(tmp_path, "list", "--category", "餐饮")[1] == "（无记录）"
    assert run(tmp_path, "balance")[1] == "100.00"


def test_errors(tmp_path):
    code, out, err = run(tmp_path, "add", "expense", "-1", "餐饮", "2026-01-05")
    assert code == 1 and err.startswith("错误：") and out == ""
    code, _, err = run(tmp_path, "delete", "9")
    assert code == 1 and err.startswith("错误：")


def test_report_and_budget(tmp_path):
    run(tmp_path, "add", "income", "5000", "工资", "2026-01-01")
    run(tmp_path, "add", "expense", "30", "餐饮", "2026-01-02")
    run(tmp_path, "add", "expense", "45", "交通", "2026-01-03")
    assert run(tmp_path, "report", "2026", "1")[1].splitlines() == ["收入 5000.00 支出 75.00 结余 4925.00", "交通 45.00", "餐饮 30.00"]
    assert run(tmp_path, "budget", "set", "交通", "40")[1] == "已设置预算 交通 40.00"
    run(tmp_path, "budget", "set", "餐饮", "100")
    assert run(tmp_path, "budget", "status", "2026", "1")[1].splitlines() == [
        "交通 已用 45.00 / 预算 40.00 超支", "餐饮 已用 30.00 / 预算 100.00"]


def test_export_import(tmp_path):
    run(tmp_path, "add", "expense", "1", "a", "2026-01-01")
    out = tmp_path / "x.csv"
    assert run(tmp_path, "export", str(out))[1] == "已导出 1 条"
    assert run(tmp_path, "import", str(out))[1] == "已导入 1 条"
    data = json.loads((tmp_path / "d.json").read_text(encoding="utf-8"))
    assert data  # 数据文件是合法 JSON
    assert len(run(tmp_path, "list")[1].splitlines()) == 2


def test_default_file(tmp_path):
    p = subprocess.run([sys.executable, "-m", "ledger", "add", "expense", "1", "a", "2026-01-01"], cwd=tmp_path,
                       capture_output=True, text=True, encoding="utf-8", env=ENV)
    assert p.returncode == 0 and (tmp_path / "ledger.json").exists(), p.stderr
