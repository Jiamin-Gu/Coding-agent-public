"""Acceptance tests for the Python API ``ledger.Ledger``.

These tests encode the requirements in docs/PRD.md and must not be modified by
the implementation tasks.
"""
import csv
from decimal import Decimal

import pytest

from ledger import Ledger


@pytest.fixture
def path(tmp_path):
    return str(tmp_path / "ledger.json")


# --------------------------------------------------------------------------
# add / get
# --------------------------------------------------------------------------

def test_add_returns_incremental_ids(path):
    l = Ledger(path)
    assert l.add("expense", "12.50", "餐饮", "2026-01-05", "午饭") == 1
    assert l.add("income", 100, "工资", "2026-01-10") == 2


def test_get_record_exact_shape(path):
    l = Ledger(path)
    l.add("expense", "12.50", "餐饮", "2026-01-05", "午饭")
    assert l.get(1) == {
        "id": 1,
        "kind": "expense",
        "amount": "12.50",
        "category": "餐饮",
        "date": "2026-01-05",
        "note": "午饭",
    }


def test_note_defaults_to_empty(path):
    l = Ledger(path)
    l.add("expense", "1.00", "餐饮", "2026-01-05")
    assert l.get(1)["note"] == ""


def test_amount_types_and_formatting(path):
    l = Ledger(path)
    assert l.get(l.add("income", 100, "工资", "2026-01-01"))["amount"] == "100.00"
    assert l.get(l.add("income", Decimal("12.5"), "工资", "2026-01-01"))["amount"] == "12.50"
    assert l.get(l.add("income", "0.3", "工资", "2026-01-01"))["amount"] == "0.30"


def test_category_is_stripped(path):
    l = Ledger(path)
    l.add("expense", "1.00", "  餐饮  ", "2026-01-05")
    assert l.get(1)["category"] == "餐饮"


@pytest.mark.parametrize("kind", ["foo", "", "Income", "支出"])
def test_invalid_kind(path, kind):
    with pytest.raises(ValueError):
        Ledger(path).add(kind, "1.00", "餐饮", "2026-01-05")


@pytest.mark.parametrize("amount", ["0", "-5", "1.234", "abc", "", "1e-3"])
def test_invalid_amount(path, amount):
    with pytest.raises(ValueError):
        Ledger(path).add("expense", amount, "餐饮", "2026-01-05")


@pytest.mark.parametrize("category", ["", "   "])
def test_invalid_category(path, category):
    with pytest.raises(ValueError):
        Ledger(path).add("expense", "1.00", category, "2026-01-05")


@pytest.mark.parametrize("date", ["2026-13-01", "2026-1-5", "20260105", "2026/01/05", ""])
def test_invalid_date(path, date):
    with pytest.raises(ValueError):
        Ledger(path).add("expense", "1.00", "餐饮", date)


def test_get_missing_raises_keyerror(path):
    with pytest.raises(KeyError):
        Ledger(path).get(99)


def test_delete_and_missing(path):
    l = Ledger(path)
    l.add("expense", "1.00", "餐饮", "2026-01-05")
    assert l.delete(1) is None
    with pytest.raises(KeyError):
        l.get(1)
    with pytest.raises(KeyError):
        l.delete(1)


def test_ids_not_reused_after_delete(path):
    l = Ledger(path)
    l.add("expense", "1.00", "餐饮", "2026-01-05")
    l.add("expense", "2.00", "餐饮", "2026-01-06")
    l.delete(1)
    assert l.add("expense", "3.00", "餐饮", "2026-01-07") == 3


# --------------------------------------------------------------------------
# persistence
# --------------------------------------------------------------------------

def test_persistence_across_instances(path):
    l = Ledger(path)
    l.add("expense", "12.50", "餐饮", "2026-01-05")
    l.add("income", "100", "工资", "2026-01-10")
    l.delete(1)
    assert Ledger(path).add("expense", "1.00", "其他", "2026-01-11") == 3
    assert [r["id"] for r in Ledger(path).list()] == [2, 3]


def test_missing_file_is_empty(path):
    l = Ledger(path)
    assert l.list() == []
    assert l.balance() == "0.00"


def test_undo_history_not_persisted(path):
    l = Ledger(path)
    l.add("expense", "1.00", "餐饮", "2026-01-05")
    assert Ledger(path).undo() is False


# --------------------------------------------------------------------------
# list / search
# --------------------------------------------------------------------------

def test_list_sort_and_filters(path):
    l = Ledger(path)
    l.add("expense", "5.00", "餐饮", "2026-01-10")
    l.add("income", "100.00", "工资", "2026-01-05")
    l.add("expense", "3.00", "交通", "2026-01-05")
    assert [r["id"] for r in l.list()] == [2, 3, 1]
    assert [r["id"] for r in l.list(start="2026-01-10")] == [1]
    assert [r["id"] for r in l.list(end="2026-01-05")] == [2, 3]
    assert [r["id"] for r in l.list(category="餐饮")] == [1]
    assert [r["id"] for r in l.list(kind="income")] == [2]
    assert [r["id"] for r in l.list(start="2026-01-05", end="2026-01-05", kind="expense")] == [3]


def test_search_case_insensitive(path):
    l = Ledger(path)
    l.add("expense", "5.00", "Food", "2026-01-10", "Lunch")
    l.add("expense", "3.00", "交通", "2026-01-05", "taxi")
    assert [r["id"] for r in l.search("lunch")] == [1]
    assert [r["id"] for r in l.search("FOOD")] == [1]
    assert [r["id"] for r in l.search("x")] == [2]
    assert [r["id"] for r in l.search("zzz")] == []


# --------------------------------------------------------------------------
# balance
# --------------------------------------------------------------------------

def test_balance(path):
    l = Ledger(path)
    l.add("income", "100.00", "工资", "2026-01-05")
    l.add("expense", "30.00", "餐饮", "2026-01-06")
    assert l.balance() == "70.00"
    assert l.balance(start="2026-01-06") == "-30.00"
    assert l.balance(end="2026-01-05") == "100.00"


def test_balance_no_rounding_error(path):
    l = Ledger(path)
    l.add("income", "0.10", "aa", "2026-01-01")
    l.add("income", "0.20", "aa", "2026-01-01")
    assert l.balance() == "0.30"


# --------------------------------------------------------------------------
# monthly_report
# --------------------------------------------------------------------------

def test_monthly_report(path):
    l = Ledger(path)
    l.add("income", "100.00", "工资", "2026-01-05")
    l.add("expense", "30.00", "餐饮", "2026-01-06")
    l.add("expense", "20.00", "交通", "2026-01-07")
    l.add("expense", "99.00", "其他", "2026-02-01")
    r = l.monthly_report(2026, 1)
    assert r["income"] == "100.00"
    assert r["expense"] == "50.00"
    assert r["net"] == "50.00"
    assert r["by_category"] == [
        {"category": "餐饮", "amount": "30.00"},
        {"category": "交通", "amount": "20.00"},
    ]


def test_monthly_report_tie_sort(path):
    l = Ledger(path)
    l.add("expense", "10.00", "b", "2026-01-01")
    l.add("expense", "10.00", "a", "2026-01-02")
    r = l.monthly_report(2026, 1)
    assert [c["category"] for c in r["by_category"]] == ["a", "b"]


# --------------------------------------------------------------------------
# budget
# --------------------------------------------------------------------------

def test_set_budget_and_status(path):
    l = Ledger(path)
    l.set_budget("餐饮", "50.00")
    l.add("expense", "30.00", "餐饮", "2026-01-06")
    st = l.budget_status(2026, 1)
    assert st == [{
        "category": "餐饮",
        "budget": "50.00",
        "spent": "30.00",
        "remaining": "20.00",
        "over": False,
    }]


def test_budget_over_and_negative_remaining(path):
    l = Ledger(path)
    l.set_budget("餐饮", "20.00")
    l.add("expense", "30.00", "餐饮", "2026-01-06")
    st = l.budget_status(2026, 1)[0]
    assert st["remaining"] == "-10.00"
    assert st["over"] is True


def test_budget_overwrite_and_sort(path):
    l = Ledger(path)
    l.set_budget("b", "10.00")
    l.set_budget("a", "5.00")
    l.set_budget("b", "15.00")
    st = l.budget_status(2026, 1)
    assert [x["category"] for x in st] == ["a", "b"]
    assert st[1]["budget"] == "15.00"


def test_budget_only_expenses_counted(path):
    l = Ledger(path)
    l.set_budget("餐饮", "50.00")
    l.add("income", "30.00", "餐饮", "2026-01-06")
    st = l.budget_status(2026, 1)[0]
    assert st["spent"] == "0.00"
    assert st["remaining"] == "50.00"


def test_budget_persists(path):
    l = Ledger(path)
    l.set_budget("餐饮", "50.00")
    st = Ledger(path).budget_status(2026, 1)
    assert st[0]["budget"] == "50.00"


@pytest.mark.parametrize("amount", ["0", "-1", "1.234"])
def test_set_budget_invalid(path, amount):
    with pytest.raises(ValueError):
        Ledger(path).set_budget("餐饮", amount)


# --------------------------------------------------------------------------
# export / import csv
# --------------------------------------------------------------------------

def test_export_csv(path, tmp_path):
    l = Ledger(path)
    l.add("expense", "12.50", "餐饮", "2026-01-05", "午饭")
    l.add("income", "100.00", "工资", "2026-01-01")
    out = tmp_path / "out.csv"
    assert l.export_csv(str(out)) == 2
    rows = list(csv.reader(out.read_text(encoding="utf-8").splitlines()))
    assert rows[0] == ["date", "kind", "category", "amount", "note"]
    assert rows[1] == ["2026-01-01", "income", "工资", "100.00", ""]
    assert rows[2] == ["2026-01-05", "expense", "餐饮", "12.50", "午饭"]


def test_import_csv_assigns_new_ids(path, tmp_path):
    src = tmp_path / "in.csv"
    src.write_text(
        "date,kind,category,amount,note\n"
        "2026-01-01,income,工资,100.00,salary\n"
        "\n"
        "2026-01-05,expense,餐饮,12.50,午饭\n",
        encoding="utf-8",
    )
    l = Ledger(path)
    assert l.import_csv(str(src)) == 2
    recs = l.list()
    assert [r["id"] for r in recs] == [1, 2]
    assert recs[0]["category"] == "工资"


def test_import_csv_atomic_on_error(path, tmp_path):
    src = tmp_path / "in.csv"
    src.write_text(
        "date,kind,category,amount,note\n"
        "2026-01-01,income,工资,100.00,\n"
        "baddate,expense,餐饮,12.50,\n",
        encoding="utf-8",
    )
    l = Ledger(path)
    with pytest.raises(ValueError) as e:
        l.import_csv(str(src))
    assert "3" in str(e.value)
    assert l.list() == []
    assert l.add("expense", "1.00", "xx", "2026-01-01") == 1


def test_import_csv_bad_header(path, tmp_path):
    src = tmp_path / "in.csv"
    src.write_text("foo,bar\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError):
        Ledger(path).import_csv(str(src))


# --------------------------------------------------------------------------
# undo
# --------------------------------------------------------------------------

def test_undo_add(path):
    l = Ledger(path)
    l.add("expense", "1.00", "餐饮", "2026-01-05")
    assert l.undo() is True
    assert l.list() == []


def test_undo_delete(path):
    l = Ledger(path)
    l.add("expense", "1.00", "餐饮", "2026-01-05")
    l.delete(1)
    assert l.undo() is True
    assert l.get(1)["amount"] == "1.00"


def test_undo_import_is_whole_batch(path, tmp_path):
    src = tmp_path / "in.csv"
    src.write_text(
        "date,kind,category,amount,note\n"
        "2026-01-01,income,工资,100.00,\n"
        "2026-01-05,expense,餐饮,12.50,\n",
        encoding="utf-8",
    )
    l = Ledger(path)
    l.import_csv(str(src))
    assert l.undo() is True
    assert l.list() == []


def test_undo_multiple_then_false(path):
    l = Ledger(path)
    l.add("expense", "1.00", "餐饮", "2026-01-05")
    l.add("expense", "2.00", "餐饮", "2026-01-06")
    assert l.undo() is True
    assert l.undo() is True
    assert l.undo() is False


def test_undo_removal_persists(path):
    l = Ledger(path)
    l.add("expense", "1.00", "餐饮", "2026-01-05")
    l.undo()
    assert Ledger(path).list() == []
