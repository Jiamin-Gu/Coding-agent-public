"""验收测试：S6 库存 receive/adjust/stock/set_reorder_level/low_stock/stock_log。"""

from datetime import datetime

import pytest

from shopkit import Shop
from shopkit.errors import NotFoundError, StockError, ValidationError


class FakeClock:
    """固定的本地时钟助手：返回固定 datetime，并记录被调用次数。"""

    def __init__(self, when=None):
        self.when = when if when is not None else datetime(2026, 3, 1, 9, 30, 0)
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.when


def make_shop(clock=None):
    return Shop(clock=clock if clock is not None else FakeClock())


def add(shop, sku="SKU-1"):
    shop.add_product(sku, sku, "10", "c")
    return sku


# --- receive -----------------------------------------------------------------


def test_receive_increases_on_hand_and_returns_stock():
    shop = make_shop()
    add(shop)
    assert shop.receive("SKU-1", 5) == {
        "on_hand": 5,
        "reserved": 0,
        "available": 5,
    }


@pytest.mark.parametrize("qty", [0, -1, 1.0, "3", True, False, None])
def test_receive_rejects_invalid_qty(qty):
    shop = make_shop()
    add(shop)
    with pytest.raises(ValidationError):
        shop.receive("SKU-1", qty)


def test_receive_missing_sku_raises_not_found():
    shop = make_shop()
    with pytest.raises(NotFoundError):
        shop.receive("NOPE", 1)


def test_receive_logs_entry_with_clock_time():
    clock = FakeClock(datetime(2026, 3, 1, 9, 30, 0))
    shop = make_shop(clock)
    add(shop)
    shop.receive("SKU-1", 4)
    assert shop.stock_log("SKU-1") == [
        {"at": "2026-03-01T09:30:00", "change": 4, "reason": "receive"}
    ]


# --- adjust ------------------------------------------------------------------


def test_adjust_changes_on_hand_and_returns_stock():
    shop = make_shop()
    add(shop)
    shop.receive("SKU-1", 10)
    assert shop.adjust("SKU-1", -3, "shrinkage") == {
        "on_hand": 7,
        "reserved": 0,
        "available": 7,
    }


def test_adjust_saves_stripped_reason_in_log():
    shop = make_shop()
    add(shop)
    shop.receive("SKU-1", 10)
    shop.adjust("SKU-1", 2, "  recount  ")
    entry = shop.stock_log("SKU-1")[-1]
    assert entry["change"] == 2
    assert entry["reason"] == "recount"


@pytest.mark.parametrize("delta", [0, 1.0, "2", True, None])
def test_adjust_rejects_invalid_delta(delta):
    shop = make_shop()
    add(shop)
    with pytest.raises(ValidationError):
        shop.adjust("SKU-1", delta, "reason")


@pytest.mark.parametrize("reason", ["", "   ", None, 5])
def test_adjust_rejects_invalid_reason(reason):
    shop = make_shop()
    add(shop)
    with pytest.raises(ValidationError):
        shop.adjust("SKU-1", 1, reason)


def test_adjust_missing_sku_raises_not_found():
    shop = make_shop()
    with pytest.raises(NotFoundError):
        shop.adjust("NOPE", 1, "reason")


def test_adjust_below_zero_raises_stock_error():
    shop = make_shop()
    add(shop)
    with pytest.raises(StockError):
        shop.adjust("SKU-1", -1, "loss")


def test_adjust_below_reserved_raises_stock_error():
    shop = make_shop()
    add(shop)
    shop.receive("SKU-1", 5)
    shop._reserve("SKU-1", 4)  # 已预留 4，可用 1
    with pytest.raises(StockError):
        shop.adjust("SKU-1", -2, "loss")  # on_hand 3 < reserved 4


def test_failed_adjust_is_atomic():
    shop = make_shop()
    add(shop)
    shop.receive("SKU-1", 2)
    before = shop.stock("SKU-1")
    log_before = list(shop.stock_log("SKU-1"))
    with pytest.raises(StockError):
        shop.adjust("SKU-1", -5, "loss")
    assert shop.stock("SKU-1") == before
    assert shop.stock_log("SKU-1") == log_before


def test_receive_checks_params_before_sku_lookup():
    # 检查顺序：参数 ValidationError 先于 NotFoundError
    shop = make_shop()
    with pytest.raises(ValidationError):
        shop.receive("NOPE", 0)


def test_adjust_checks_params_before_sku_lookup():
    shop = make_shop()
    with pytest.raises(ValidationError):
        shop.adjust("NOPE", 0, "reason")


# --- stock -------------------------------------------------------------------


def test_stock_available_is_on_hand_minus_reserved():
    shop = make_shop()
    add(shop)
    shop.receive("SKU-1", 5)
    shop._reserve("SKU-1", 2)
    assert shop.stock("SKU-1") == {"on_hand": 5, "reserved": 2, "available": 3}


def test_stock_missing_sku_raises_not_found():
    shop = make_shop()
    with pytest.raises(NotFoundError):
        shop.stock("NOPE")


# --- set_reorder_level -------------------------------------------------------


def test_set_reorder_level_returns_stock():
    shop = make_shop()
    add(shop)
    shop.receive("SKU-1", 7)
    assert shop.set_reorder_level("SKU-1", 3) == {
        "on_hand": 7,
        "reserved": 0,
        "available": 7,
    }


@pytest.mark.parametrize("level", [-1, 1.0, "2", True, None])
def test_set_reorder_level_rejects_invalid_level(level):
    shop = make_shop()
    add(shop)
    with pytest.raises(ValidationError):
        shop.set_reorder_level("SKU-1", level)


def test_set_reorder_level_missing_sku_raises_not_found():
    shop = make_shop()
    with pytest.raises(NotFoundError):
        shop.set_reorder_level("NOPE", 1)


# --- low_stock ---------------------------------------------------------------


def test_low_stock_filters_and_sorts():
    shop = make_shop()
    # AAA: available 5, level 5 -> 包含（<=）
    shop.add_product("AAA", "a", "1", "c")
    shop.receive("AAA", 5)
    shop.set_reorder_level("AAA", 5)
    # BBB: available 10, level 3 -> 不含
    shop.add_product("BBB", "b", "1", "c")
    shop.receive("BBB", 10)
    shop.set_reorder_level("BBB", 3)
    # CCC: available 2, level 10 -> 含
    shop.add_product("CCC", "c", "1", "c")
    shop.receive("CCC", 2)
    shop.set_reorder_level("CCC", 10)
    # DDD: available 1, level 0 -> 不含（level 必须 > 0）
    shop.add_product("DDD", "d", "1", "c")
    shop.receive("DDD", 1)

    assert shop.low_stock() == [
        {"sku": "AAA", "available": 5, "reorder_level": 5},
        {"sku": "CCC", "available": 2, "reorder_level": 10},
    ]


def test_low_stock_includes_inactive_products():
    shop = make_shop()
    shop.add_product("OFF", "o", "1", "c", active=False)
    shop.receive("OFF", 1)
    shop.set_reorder_level("OFF", 1)
    assert shop.low_stock() == [
        {"sku": "OFF", "available": 1, "reorder_level": 1}
    ]


# --- stock_log ---------------------------------------------------------------


def test_stock_log_records_events_in_order():
    shop = make_shop()
    add(shop)
    shop.receive("SKU-1", 5)
    shop.adjust("SKU-1", 1, "fix")
    shop.adjust("SKU-1", -2, "loss")
    assert shop.stock_log("SKU-1") == [
        {"at": "2026-03-01T09:30:00", "change": 5, "reason": "receive"},
        {"at": "2026-03-01T09:30:00", "change": 1, "reason": "fix"},
        {"at": "2026-03-01T09:30:00", "change": -2, "reason": "loss"},
    ]


def test_reserve_and_release_do_not_log():
    shop = make_shop()
    add(shop)
    shop.receive("SKU-1", 5)
    shop._reserve("SKU-1", 2)
    shop._release("SKU-1", 1)
    assert [e["reason"] for e in shop.stock_log("SKU-1")] == ["receive"]


def test_stock_log_missing_sku_raises_not_found():
    shop = make_shop()
    with pytest.raises(NotFoundError):
        shop.stock_log("NOPE")
