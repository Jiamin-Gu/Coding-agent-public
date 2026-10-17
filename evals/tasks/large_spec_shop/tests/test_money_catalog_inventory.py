from decimal import Decimal

import pytest

import shopkit
from shopkit import errors
from shopkit.money import format_money, parse_money, round_money


# ---------------------------------------------------------------- 金额与异常

def test_parse_money_valid():
    assert parse_money("5") == Decimal("5.00")
    assert parse_money(" 12.5 ") == Decimal("12.50")
    assert parse_money(3) == Decimal("3.00")
    assert parse_money(Decimal("0.1")) == Decimal("0.10")
    assert parse_money("0") == Decimal("0.00")
    assert str(parse_money("7.1")) == "7.10"


@pytest.mark.parametrize("bad", [True, 1.5, None, "abc", "", "-1", "1.234", "NaN", "Infinity", [], Decimal("-0.5")])
def test_parse_money_invalid(bad):
    with pytest.raises(errors.ValidationError):
        parse_money(bad)


def test_round_and_format():
    assert round_money(Decimal("0.125")) == Decimal("0.13")
    assert round_money(Decimal("2.675")) == Decimal("2.68")
    assert round_money(Decimal("1.004")) == Decimal("1.00")
    assert format_money(Decimal("3")) == "3.00"
    assert format_money(Decimal("-3.5")) == "-3.50"
    assert format_money(Decimal("1.005")) == "1.01"


def test_error_hierarchy_and_exports():
    for name in ("ValidationError", "NotFoundError", "StockError", "StateError", "CouponError"):
        cls = getattr(errors, name)
        assert issubclass(cls, errors.ShopError) and getattr(shopkit, name) is cls
    assert issubclass(errors.ShopError, Exception) and shopkit.ShopError is errors.ShopError


# ---------------------------------------------------------------- 商品

def test_add_and_get_product(stocked):
    assert stocked.get_product("BOOK-1") == {"sku": "BOOK-1", "name": "Python 入门", "price": "59.90",
                                             "category": "book", "active": True}
    assert stocked.get_product("APPLE")["category"] == "food"
    assert stocked.add_product("PEN", "  钢笔 ", 8, "Office", active=False) == {
        "sku": "PEN", "name": "钢笔", "price": "8.00", "category": "office", "active": False}


@pytest.mark.parametrize("args", [
    ("apple", "x", "1", "c"), ("A B", "x", "1", "c"), ("", "x", "1", "c"), ("A" * 21, "x", "1", "c"), (5, "x", "1", "c"),
    ("A", "  ", "1", "c"), ("A", "x", "0", "c"), ("A", "x", "-1", "c"), ("A", "x", "1.234", "c"), ("A", "x", 1.5, "c"),
    ("A", "x", "1", "   "),
])
def test_add_product_invalid(shop, args):
    with pytest.raises(errors.ValidationError):
        shop.add_product(*args)
    assert shop.list_products() == []


def test_add_product_active_must_be_bool_and_sku_unique(stocked):
    with pytest.raises(errors.ValidationError):
        stocked.add_product("NEW", "x", "1", "c", active="yes")
    with pytest.raises(errors.ValidationError):
        stocked.add_product("APPLE", "另一个苹果", "1", "food")
    assert stocked.get_product("APPLE")["name"] == "苹果"


def test_update_price_set_active_and_not_found(stocked):
    assert stocked.update_price("MILK", "13.5")["price"] == "13.50"
    assert stocked.set_active("MILK", False)["active"] is False
    with pytest.raises(errors.ValidationError):
        stocked.update_price("MILK", "0")
    with pytest.raises(errors.ValidationError):
        stocked.set_active("MILK", 1)
    for call in (lambda: stocked.get_product("NOPE"), lambda: stocked.update_price("NOPE", "1"),
                 lambda: stocked.set_active("NOPE", True)):
        with pytest.raises(errors.NotFoundError):
            call()


def test_list_products(stocked):
    assert [p["sku"] for p in stocked.list_products()] == ["APPLE", "BOOK-1", "MILK"]
    assert [p["sku"] for p in stocked.list_products(category=" FOOD ")] == ["APPLE", "MILK"]
    stocked.set_active("MILK", False)
    assert [p["sku"] for p in stocked.list_products(active_only=True)] == ["APPLE", "BOOK-1"]
    assert stocked.list_products(category="toys") == []


# ---------------------------------------------------------------- 库存

def test_stock_receive_and_log(stocked, clock):
    assert stocked.stock("APPLE") == {"on_hand": 100, "reserved": 0, "available": 100}
    stocked.add_product("NEW", "新品", "1", "misc")
    assert stocked.stock("NEW") == {"on_hand": 0, "reserved": 0, "available": 0}
    clock.set("2026-03-02T10:30:00")
    assert stocked.receive("MILK", 5) == {"on_hand": 25, "reserved": 0, "available": 25}
    assert stocked.stock_log("MILK") == [
        {"at": "2026-03-01T09:00:00", "change": 20, "reason": "receive"},
        {"at": "2026-03-02T10:30:00", "change": 5, "reason": "receive"}]


@pytest.mark.parametrize("qty", [0, -1, True, "5", 2.0])
def test_receive_invalid_qty(stocked, qty):
    with pytest.raises(errors.ValidationError):
        stocked.receive("MILK", qty)
    assert stocked.stock("MILK")["on_hand"] == 20 and len(stocked.stock_log("MILK")) == 1


def test_inventory_not_found(stocked):
    for call in (lambda: stocked.receive("NOPE", 1), lambda: stocked.adjust("NOPE", 1, "x"),
                 lambda: stocked.stock("NOPE"), lambda: stocked.set_reorder_level("NOPE", 1),
                 lambda: stocked.stock_log("NOPE")):
        with pytest.raises(errors.NotFoundError):
            call()


def test_adjust(stocked):
    assert stocked.adjust("MILK", -5, " 盘亏 ") == {"on_hand": 15, "reserved": 0, "available": 15}
    assert stocked.stock_log("MILK")[-1] == {"at": "2026-03-01T09:00:00", "change": -5, "reason": "盘亏"}
    for delta, reason in ((0, "x"), (True, "x"), ("3", "x"), (1, "  "), (1, None)):
        with pytest.raises(errors.ValidationError):
            stocked.adjust("MILK", delta, reason)
    with pytest.raises(errors.StockError):
        stocked.adjust("BOOK-1", -6, "丢失")
    assert stocked.stock("BOOK-1")["on_hand"] == 5 and len(stocked.stock_log("BOOK-1")) == 1


def test_adjust_cannot_go_below_reserved(stocked):
    oid = stocked.create_order("张三", [{"sku": "BOOK-1", "qty": 3}])
    stocked.place_order(oid)
    assert stocked.stock("BOOK-1") == {"on_hand": 5, "reserved": 3, "available": 2}
    with pytest.raises(errors.StockError):
        stocked.adjust("BOOK-1", -3, "损坏")
    assert stocked.adjust("BOOK-1", -2, "损坏") == {"on_hand": 3, "reserved": 3, "available": 0}


def test_reorder_level_and_low_stock(stocked):
    assert stocked.low_stock() == []
    assert stocked.set_reorder_level("MILK", 20) == {"on_hand": 20, "reserved": 0, "available": 20}
    stocked.set_reorder_level("APPLE", 10)
    stocked.set_reorder_level("BOOK-1", 5)
    stocked.set_active("BOOK-1", False)  # 下架的也算
    assert stocked.low_stock() == [{"sku": "BOOK-1", "available": 5, "reorder_level": 5},
                                   {"sku": "MILK", "available": 20, "reorder_level": 20}]
    stocked.set_reorder_level("MILK", 0)
    assert [x["sku"] for x in stocked.low_stock()] == ["BOOK-1"]
    for level in (-1, True, "3"):
        with pytest.raises(errors.ValidationError):
            stocked.set_reorder_level("MILK", level)
