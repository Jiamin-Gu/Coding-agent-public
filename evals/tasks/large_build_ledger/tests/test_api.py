import csv
from decimal import Decimal

import pytest

from ledger import Ledger


@pytest.fixture
def path(tmp_path):
    return tmp_path / "data.json"


@pytest.fixture
def lg(path):
    return Ledger(path)


def test_add_get_and_format(lg):
    i = lg.add("expense", "12.5", " 餐饮 ", "2026-01-05", "午饭")
    assert i == 1
    assert lg.get(1) == {"id": 1, "kind": "expense", "amount": "12.50", "category": "餐饮",
                         "date": "2026-01-05", "note": "午饭"}
    assert lg.add("income", 100, "工资", "2026-01-10") == 2
    assert lg.get(2)["note"] == "" and lg.get(2)["amount"] == "100.00"
    assert lg.add("income", Decimal("0.1"), "红包", "2026-01-11") == 3


@pytest.mark.parametrize("args", [
    ("salary", "1", "x", "2026-01-01"), ("expense", "0", "x", "2026-01-01"), ("expense", "-5", "x", "2026-01-01"),
    ("expense", "1.005", "x", "2026-01-01"), ("expense", "abc", "x", "2026-01-01"), ("expense", "1", "  ", "2026-01-01"),
    ("expense", "1", "x", "2026-02-30"), ("expense", "1", "x", "2026/01/01"), ("expense", "1", "x", "20260101"),
])
def test_invalid_add(lg, args):
    with pytest.raises(ValueError):
        lg.add(*args)
    assert lg.list() == []


def test_get_delete_missing(lg):
    with pytest.raises(KeyError):
        lg.get(1)
    with pytest.raises(KeyError):
        lg.delete(1)


def test_ids_not_reused(lg):
    lg.add("expense", "1", "a", "2026-01-01")
    lg.add("expense", "2", "a", "2026-01-01")
    lg.delete(2)
    assert lg.add("expense", "3", "a", "2026-01-01") == 3


def test_list_filters_and_order(lg):
    lg.add("expense", "1", "餐饮", "2026-01-05")
    lg.add("income", "2", "工资", "2026-01-03")
    lg.add("expense", "3", "交通", "2026-01-05")
    lg.add("expense", "4", "餐饮", "2026-02-01")
    assert [r["id"] for r in lg.list()] == [2, 1, 3, 4]
    assert [r["id"] for r in lg.list(start="2026-01-04", end="2026-01-31")] == [1, 3]
    assert [r["id"] for r in lg.list(category="餐饮")] == [1, 4]
    assert [r["id"] for r in lg.list(kind="income")] == [2]
    assert [r["id"] for r in lg.list(start="2026-01-05", end="2026-01-05", kind="expense")] == [1, 3]


def test_search(lg):
    lg.add("expense", "1", "餐饮", "2026-01-02", "Coffee with Tom")
    lg.add("expense", "1", "咖啡", "2026-01-01")
    lg.add("expense", "1", "交通", "2026-01-03", "地铁")
    assert [r["id"] for r in lg.search("coffee")] == [1]
    assert [r["id"] for r in lg.search("咖啡")] == [2]
    assert lg.search("不存在") == []


def test_exact_amounts_and_balance(lg):
    for _ in range(3):
        lg.add("income", "0.10", "x", "2026-01-01")
    lg.add("expense", "0.30", "y", "2026-01-02")
    assert lg.balance() == "0.00"
    lg.add("expense", "12.00", "y", "2026-02-01")
    assert lg.balance() == "-12.00"
    assert lg.balance(start="2026-01-01", end="2026-01-01") == "0.30"


def test_monthly_report(lg):
    lg.add("income", "5000", "工资", "2026-01-01")
    lg.add("expense", "30", "餐饮", "2026-01-02")
    lg.add("expense", "20.5", "交通", "2026-01-03")
    lg.add("expense", "20.5", "书籍", "2026-01-04")
    lg.add("expense", "15", "餐饮", "2026-01-31")
    lg.add("expense", "999", "餐饮", "2026-02-01")
    assert lg.monthly_report(2026, 1) == {
        "income": "5000.00", "expense": "86.00", "net": "4914.00",
        "by_category": [{"category": "餐饮", "amount": "45.00"}, {"category": "书籍", "amount": "20.50"},
                        {"category": "交通", "amount": "20.50"}],
    }
    assert lg.monthly_report(2025, 12) == {"income": "0.00", "expense": "0.00", "net": "0.00", "by_category": []}


def test_budgets(lg):
    lg.set_budget("餐饮", "100")
    lg.set_budget("交通", "50")
    lg.set_budget("交通", "40")
    lg.add("expense", "60", "餐饮", "2026-01-02")
    lg.add("expense", "45", "交通", "2026-01-03")
    lg.add("income", "45", "交通", "2026-01-03")       # 收入不算支出
    lg.add("expense", "500", "餐饮", "2026-02-01")       # 别的月份
    assert lg.budget_status(2026, 1) == [
        {"category": "交通", "budget": "40.00", "spent": "45.00", "remaining": "-5.00", "over": True},
        {"category": "餐饮", "budget": "100.00", "spent": "60.00", "remaining": "40.00", "over": False},
    ]
    with pytest.raises(ValueError):
        lg.set_budget("餐饮", "0")


def test_persistence(path):
    lg = Ledger(path)
    lg.add("expense", "1", "a", "2026-01-01")
    lg.add("expense", "2", "a", "2026-01-01")
    lg.delete(2)
    lg.set_budget("a", "10")
    again = Ledger(path)
    assert [r["id"] for r in again.list()] == [1]
    assert again.add("expense", "3", "a", "2026-01-01") == 3
    assert again.budget_status(2026, 1)[0]["spent"] == "4.00"   # 1 + 3
    assert again.undo() is True and again.undo() is False   # 撤销历史不跨对象


def test_undo(lg):
    a = lg.add("expense", "1", "a", "2026-01-01")
    b = lg.add("expense", "2", "a", "2026-01-02")
    lg.delete(a)
    assert lg.undo() is True and [r["id"] for r in lg.list()] == [a, b]
    assert lg.undo() is True and [r["id"] for r in lg.list()] == [a]
    assert lg.undo() is True and lg.list() == []
    assert lg.undo() is False
    assert lg.add("expense", "1", "a", "2026-01-01") == 3


def test_export_import_round_trip(lg, tmp_path):
    lg.add("expense", "12.5", "餐饮", "2026-01-05", "含, 逗号")
    lg.add("income", "100", "工资", "2026-01-01")
    out = tmp_path / "out.csv"
    assert lg.export_csv(out) == 2
    with open(out, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    assert rows == [["date", "kind", "category", "amount", "note"],
                    ["2026-01-01", "income", "工资", "100.00", ""],
                    ["2026-01-05", "expense", "餐饮", "12.50", "含, 逗号"]]
    other = Ledger(tmp_path / "other.json")
    other.add("expense", "1", "x", "2026-01-01")
    assert other.import_csv(out) == 2
    assert [(r["id"], r["note"]) for r in other.list()] == [(1, ""), (2, ""), (3, "含, 逗号")]
    assert other.undo() is True and [r["id"] for r in other.list()] == [1]


def test_import_is_atomic_and_reports_line(lg, tmp_path):
    lg.add("expense", "1", "x", "2026-01-01")
    bad = tmp_path / "bad.csv"
    bad.write_text("date,kind,category,amount,note\n2026-01-02,expense,a,5,\n\n2026-01-03,expense,b,-1,\n",
                   encoding="utf-8")
    with pytest.raises(ValueError, match="4"):
        lg.import_csv(bad)
    assert len(lg.list()) == 1
    nohead = tmp_path / "nohead.csv"
    nohead.write_text("2026-01-02,expense,a,5,\n", encoding="utf-8")
    with pytest.raises(ValueError):
        lg.import_csv(nohead)
    assert len(lg.list()) == 1
