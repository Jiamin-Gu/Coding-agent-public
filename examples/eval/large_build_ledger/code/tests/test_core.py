"""ledger.Ledger 的核心功能测试。"""

from decimal import Decimal

import pytest

from ledger import Ledger


@pytest.fixture
def db(tmp_path):
    return tmp_path / "ledger.json"


# ---------------------------------------------------------------- 基本增查
def test_add_returns_increasing_ids(db):
    led = Ledger(db)
    assert led.add("expense", "12.50", "餐饮", "2026-01-05", "午饭") == 1
    assert led.add("income", "100", "工资", "2026-01-06") == 2


def test_add_get_returns_normalized_dict(db):
    led = Ledger(db)
    led.add("expense", "12.5", "  餐饮  ", "2026-01-05", "午饭")
    assert led.get(1) == {
        "id": 1,
        "kind": "expense",
        "amount": "12.50",
        "category": "餐饮",
        "date": "2026-01-05",
        "note": "午饭",
    }


def test_amount_accepts_str_int_decimal(db):
    led = Ledger(db)
    led.add("income", "1.5", "a", "2026-01-01")
    led.add("income", 100, "b", "2026-01-02")
    led.add("income", Decimal("0.30"), "c", "2026-01-03")
    assert led.get(1)["amount"] == "1.50"
    assert led.get(2)["amount"] == "100.00"
    assert led.get(3)["amount"] == "0.30"


def test_get_missing_raises_keyerror(db):
    led = Ledger(db)
    with pytest.raises(KeyError):
        led.get(1)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"kind": "other", "amount": "1", "category": "a", "date": "2026-01-01"},
        {"kind": "expense", "amount": "0", "category": "a", "date": "2026-01-01"},
        {"kind": "expense", "amount": "-1", "category": "a", "date": "2026-01-01"},
        {"kind": "expense", "amount": "1.234", "category": "a", "date": "2026-01-01"},
        {"kind": "expense", "amount": "abc", "category": "a", "date": "2026-01-01"},
        {"kind": "expense", "amount": 1.5, "category": "a", "date": "2026-01-01"},
        {"kind": "expense", "amount": "1", "category": "   ", "date": "2026-01-01"},
        {"kind": "expense", "amount": "1", "category": "a", "date": "2026-1-5"},
        {"kind": "expense", "amount": "1", "category": "a", "date": "2026-13-01"},
        {"kind": "expense", "amount": "1", "category": "a", "date": "2026-02-30"},
        {"kind": "expense", "amount": "1", "category": "a", "date": "hello"},
    ],
)
def test_invalid_arguments_raise_valueerror(db, kwargs):
    led = Ledger(db)
    with pytest.raises(ValueError):
        led.add(**kwargs)
    # 非法参数不应产生任何记录，也不消耗 id
    assert led.list() == []


# ---------------------------------------------------------------- 删除 / id
def test_delete_and_keyerror(db):
    led = Ledger(db)
    rid = led.add("expense", "1", "a", "2026-01-01")
    led.delete(rid)
    assert led.list() == []
    with pytest.raises(KeyError):
        led.delete(rid)


def test_id_not_reused_after_delete(db):
    led = Ledger(db)
    first = led.add("expense", "1", "a", "2026-01-01")
    led.delete(first)
    assert led.add("expense", "1", "a", "2026-01-02") == 2


def test_id_not_reused_after_undo(db):
    led = Ledger(db)
    assert led.add("expense", "1", "a", "2026-01-01") == 1
    assert led.undo() is True
    assert led.list() == []
    assert led.add("expense", "1", "a", "2026-01-02") == 2


# ---------------------------------------------------------------- 列表 / 搜索
def test_list_filter_and_order(db):
    led = Ledger(db)
    led.add("expense", "5", "交通", "2026-01-10")
    led.add("income", "100", "工资", "2026-01-05")
    led.add("expense", "3", "餐饮", "2026-01-05")

    ids = [r["id"] for r in led.list()]
    assert ids == [2, 3, 1]  # 按 (date, id) 升序

    only_expense = led.list(kind="expense")
    assert [r["category"] for r in only_expense] == ["餐饮", "交通"]

    ranged = led.list(start="2026-01-05", end="2026-01-05")
    assert [r["id"] for r in ranged] == [2, 3]

    by_category = led.list(category="交通")
    assert len(by_category) == 1


def test_search_case_insensitive(db):
    led = Ledger(db)
    led.add("expense", "5", "Food", "2026-01-10", "Lunch")
    led.add("income", "100", "工资", "2026-01-05", "月薪")

    assert len(led.search("food")) == 1
    assert len(led.search("LUNCH")) == 1
    assert len(led.search("月")) == 1
    assert led.search("nothing") == []


# ---------------------------------------------------------------- 余额 / 报表
def test_balance_is_exact(db):
    led = Ledger(db)
    led.add("income", "0.10", "a", "2026-01-01")
    led.add("income", "0.20", "a", "2026-01-02")
    assert led.balance() == "0.30"

    led.add("expense", "0.30", "b", "2026-01-03")
    assert led.balance() == "0.00"

    led.add("expense", "12", "c", "2026-01-04")
    assert led.balance() == "-12.00"


def test_balance_date_range(db):
    led = Ledger(db)
    led.add("income", "100", "a", "2026-01-01")
    led.add("expense", "30", "b", "2026-02-01")
    assert led.balance(start="2026-01-01", end="2026-01-31") == "100.00"
    assert led.balance(start="2026-02-01") == "-30.00"


def test_monthly_report(db):
    led = Ledger(db)
    led.add("income", "1000", "工资", "2026-03-01")
    led.add("expense", "12.50", "餐饮", "2026-03-05")
    led.add("expense", "30", "餐饮", "2026-03-10")
    led.add("expense", "8", "交通", "2026-03-11")
    led.add("expense", "5", "交通", "2026-02-28")
    led.add("income", "200", "兼职", "2026-03-15")

    report = led.monthly_report(2026, 3)
    assert report["income"] == "1200.00"
    assert report["expense"] == "50.50"
    assert report["net"] == "1149.50"
    assert report["by_category"] == [
        {"category": "餐饮", "amount": "42.50"},
        {"category": "交通", "amount": "8.00"},
    ]


def test_monthly_report_category_tie_break(db):
    led = Ledger(db)
    led.add("expense", "10", "b", "2026-03-01")
    led.add("expense", "10", "a", "2026-03-02")
    assert led.monthly_report(2026, 3)["by_category"] == [
        {"category": "a", "amount": "10.00"},
        {"category": "b", "amount": "10.00"},
    ]


# ---------------------------------------------------------------- 预算
def test_budget_status(db):
    led = Ledger(db)
    led.set_budget("餐饮", "100.00")
    led.set_budget("交通", "50")
    assert led.set_budget("餐饮", "80") is None  # 覆盖

    led.add("expense", "60", "餐饮", "2026-03-05")
    led.add("expense", "55", "交通", "2026-03-06")
    led.add("income", "999", "工资", "2026-03-07")

    status = led.budget_status(2026, 3)
    assert status == [
        {
            "category": "交通",
            "budget": "50.00",
            "spent": "55.00",
            "remaining": "-5.00",
            "over": True,
        },
        {
            "category": "餐饮",
            "budget": "80.00",
            "spent": "60.00",
            "remaining": "20.00",
            "over": False,
        },
    ]


def test_set_budget_rejects_invalid(db):
    led = Ledger(db)
    with pytest.raises(ValueError):
        led.set_budget("餐饮", "0")
    with pytest.raises(ValueError):
        led.set_budget("  ", "10")


# ---------------------------------------------------------------- 持久化
def test_persistence(db):
    led = Ledger(db)
    led.add("expense", "12.50", "餐饮", "2026-01-05", "午饭")
    led.add("income", "100", "工资", "2026-01-06")
    led.set_budget("餐饮", "200")
    led.delete(1)

    reopened = Ledger(db)
    assert len(reopened.list()) == 1
    assert reopened.balance() == "100.00"
    assert reopened.budget_status(2026, 1)[0]["budget"] == "200.00"
    # id 计数被保留，不会复用已删除的 #1
    assert reopened.add("expense", "1", "a", "2026-01-07") == 3


def test_missing_file_is_empty(db):
    assert not db.exists()
    led = Ledger(db)
    assert led.list() == []
    assert led.balance() == "0.00"
    assert led.undo() is False


# ---------------------------------------------------------------- CSV
def test_export_csv(db, tmp_path):
    led = Ledger(db)
    led.add("expense", "12.50", "餐饮", "2026-01-05", "午饭")
    led.add("income", "100", "工资", "2026-01-01", "")

    out = tmp_path / "out.csv"
    assert led.export_csv(out) == 2

    text = out.read_text(encoding="utf-8").splitlines()
    assert text[0] == "date,kind,category,amount,note"
    assert text[1] == "2026-01-01,income,工资,100.00,"
    assert text[2] == "2026-01-05,expense,餐饮,12.50,午饭"


def test_import_csv(db, tmp_path):
    src = tmp_path / "in.csv"
    src.write_text(
        "date,kind,category,amount,note\n"
        "2026-01-05,expense,餐饮,12.50,午饭\n"
        "\n"
        "2026-01-01,income,工资,100,\n",
        encoding="utf-8",
    )

    led = Ledger(db)
    led.add("expense", "1", "旧", "2025-12-31")
    assert led.import_csv(src) == 2

    records = led.list()
    assert [r["id"] for r in records] == [1, 3, 2]
    assert records[2]["note"] == "午饭"


def test_import_csv_invalid_is_atomic(db, tmp_path):
    src = tmp_path / "bad.csv"
    src.write_text(
        "date,kind,category,amount,note\n"
        "2026-01-05,expense,餐饮,12.50,午饭\n"
        "2026-01-06,expense,餐饮,-1,错误\n",
        encoding="utf-8",
    )

    led = Ledger(db)
    with pytest.raises(ValueError) as excinfo:
        led.import_csv(src)
    assert "3" in str(excinfo.value)
    assert led.list() == []


def test_import_csv_rejects_bad_header(db, tmp_path):
    src = tmp_path / "bad_header.csv"
    src.write_text("foo,bar\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError):
        Ledger(db).import_csv(src)


# ---------------------------------------------------------------- 撤销
def test_undo_add(db):
    led = Ledger(db)
    led.add("expense", "1", "a", "2026-01-01")
    assert led.undo() is True
    assert led.list() == []
    assert led.undo() is False


def test_undo_delete_restores_record(db):
    led = Ledger(db)
    rid = led.add("expense", "1", "a", "2026-01-01", "note")
    led.delete(rid)
    assert led.list() == []
    assert led.undo() is True
    assert led.get(rid)["note"] == "note"


def test_undo_import(db, tmp_path):
    src = tmp_path / "in.csv"
    src.write_text(
        "date,kind,category,amount,note\n"
        "2026-01-05,expense,餐饮,12.50,\n"
        "2026-01-06,income,工资,100,\n",
        encoding="utf-8",
    )
    led = Ledger(db)
    led.import_csv(src)
    assert len(led.list()) == 2
    assert led.undo() is True
    assert led.list() == []


def test_undo_history_not_persisted(db):
    led = Ledger(db)
    led.add("expense", "1", "a", "2026-01-01")
    reopened = Ledger(db)
    assert reopened.undo() is False
    assert len(reopened.list()) == 1
