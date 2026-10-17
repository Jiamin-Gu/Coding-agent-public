"""S13 报表验收测试：销售报表、热销商品、库存价值。"""

from datetime import datetime

import pytest

from shopkit import Shop
from shopkit.errors import ValidationError


class FakeClock:
    """可手动设置当前时间的时钟。"""

    def __init__(self, value=None):
        self.value = value or datetime(2026, 1, 1, 12, 0, 0)

    def __call__(self):
        return self.value

    def set(self, value):
        self.value = value


def _shop(clock):
    """三个上架商品，各 100 件库存。"""
    s = Shop(clock=clock)
    s.add_product("A-1", "苹果", "10.00", "food")
    s.add_product("B-2", "书", "5.00", "books")
    s.add_product("C-3", "玩具", "8.00", "toys")
    s.receive("A-1", 100)
    s.receive("B-2", 100)
    s.receive("C-3", 100)
    return s


def _ship(shop, clock, items, when, customer="张三", coupon=None):
    """在 ``when``（YYYY-MM-DD）当天创建一个已发货订单，返回订单号。"""
    clock.set(datetime.fromisoformat(when + "T09:00:00"))
    oid = shop.create_order(customer, items, coupon=coupon)
    shop.place_order(oid)
    shop.pay(oid, shop.get_order(oid)["pricing"]["total"])
    shop.ship(oid)
    return oid


# --- sales_report ---------------------------------------------------------

def test_sales_report_rejects_bad_dates():
    s = _shop(FakeClock())
    for bad in (None, 20260301, "2026-3-1", "2026-13-01", "not-a-date"):
        with pytest.raises(ValidationError):
            s.sales_report(bad, "2026-12-31")
    with pytest.raises(ValidationError):
        s.sales_report("2026-01-01", "2026-1-1")


def test_sales_report_rejects_start_after_end():
    s = _shop(FakeClock())
    with pytest.raises(ValidationError):
        s.sales_report("2026-03-05", "2026-03-01")


def test_sales_report_counts_shipped_orders():
    clock = FakeClock()
    s = _shop(clock)
    _ship(s, clock, [{"sku": "A-1", "qty": 2}], "2026-03-01")
    _ship(s, clock, [{"sku": "B-2", "qty": 3}], "2026-03-05")
    _ship(s, clock, [{"sku": "C-3", "qty": 1}], "2026-03-10")

    report = s.sales_report("2026-03-01", "2026-03-10")
    assert report["orders"] == 3
    assert report["units"] == 6
    assert report["subtotal"] == "43.00"
    assert report["coupon_discount"] == "0.00"
    assert report["tax"] == "0.00"
    assert report["revenue"] == "43.00"
    assert report["by_category"] == [
        {"category": "food", "units": 2, "net": "20.00"},
        {"category": "books", "units": 3, "net": "15.00"},
        {"category": "toys", "units": 1, "net": "8.00"},
    ]


def test_sales_report_ignores_unshipped_orders():
    clock = FakeClock()
    s = _shop(clock)
    s.create_order("张三", [{"sku": "A-1", "qty": 1}])
    placed = s.create_order("张三", [{"sku": "A-1", "qty": 1}])
    s.place_order(placed)
    paid = s.create_order("张三", [{"sku": "A-1", "qty": 1}])
    s.place_order(paid)
    s.pay(paid, "10.00")
    cancelled = s.create_order("张三", [{"sku": "A-1", "qty": 1}])
    s.cancel(cancelled, "不要了")

    report = s.sales_report("2026-01-01", "2026-12-31")
    assert report["orders"] == 0
    assert report["units"] == 0
    assert report["subtotal"] == "0.00"
    assert report["coupon_discount"] == "0.00"
    assert report["tax"] == "0.00"
    assert report["revenue"] == "0.00"
    assert report["by_category"] == []


def test_sales_report_boundaries_inclusive_and_delivered():
    clock = FakeClock()
    s = _shop(clock)
    _ship(s, clock, [{"sku": "A-1", "qty": 1}], "2026-03-01")
    delivered = _ship(s, clock, [{"sku": "B-2", "qty": 1}], "2026-03-10")
    s.deliver(delivered)

    assert s.sales_report("2026-03-01", "2026-03-10")["orders"] == 2
    assert s.sales_report("2026-03-02", "2026-03-09")["orders"] == 0


def test_sales_report_by_category_tie_sorted_by_category_asc():
    clock = FakeClock()
    s = _shop(clock)
    s.add_product("D-4", "衣服", "10.00", "clothes")
    s.receive("D-4", 10)
    _ship(s, clock, [{"sku": "A-1", "qty": 1}], "2026-03-01")
    _ship(s, clock, [{"sku": "D-4", "qty": 1}], "2026-03-02")

    report = s.sales_report("2026-03-01", "2026-03-02")
    assert report["by_category"] == [
        {"category": "clothes", "units": 1, "net": "10.00"},
        {"category": "food", "units": 1, "net": "10.00"},
    ]


def test_sales_report_sums_tax_and_coupon():
    clock = FakeClock()
    s = _shop(clock)
    s.set_tax_rate("food", "10")
    s.add_coupon("SAVE5", "fixed", "5.00")
    _ship(s, clock, [{"sku": "A-1", "qty": 1}], "2026-03-01", coupon="SAVE5")

    report = s.sales_report("2026-03-01", "2026-03-01")
    assert report["subtotal"] == "10.00"
    assert report["coupon_discount"] == "5.00"
    assert report["tax"] == "0.50"
    assert report["revenue"] == "5.50"
    # by_category 用的是优惠券分摊之前的 net
    assert report["by_category"] == [
        {"category": "food", "units": 1, "net": "10.00"},
    ]


# --- top_products ---------------------------------------------------------

def test_top_products_sorted_units_desc():
    clock = FakeClock()
    s = _shop(clock)
    _ship(
        s,
        clock,
        [{"sku": "A-1", "qty": 2}, {"sku": "B-2", "qty": 3}],
        "2026-03-01",
    )
    _ship(s, clock, [{"sku": "C-3", "qty": 1}], "2026-03-02")

    assert s.top_products() == [
        {"sku": "B-2", "units": 3},
        {"sku": "A-1", "units": 2},
        {"sku": "C-3", "units": 1},
    ]


def test_top_products_tie_by_sku_asc_and_limit():
    clock = FakeClock()
    s = _shop(clock)
    _ship(
        s,
        clock,
        [{"sku": "C-3", "qty": 1}, {"sku": "A-1", "qty": 1}],
        "2026-03-01",
    )

    assert s.top_products() == [
        {"sku": "A-1", "units": 1},
        {"sku": "C-3", "units": 1},
    ]
    assert s.top_products(limit=1) == [{"sku": "A-1", "units": 1}]


def test_top_products_rejects_bad_limit():
    s = _shop(FakeClock())
    for bad in (True, 0, -1, "5", 1.5):
        with pytest.raises(ValidationError):
            s.top_products(limit=bad)


def test_top_products_date_filter():
    clock = FakeClock()
    s = _shop(clock)
    _ship(s, clock, [{"sku": "A-1", "qty": 2}], "2026-03-01")
    _ship(s, clock, [{"sku": "B-2", "qty": 3}], "2026-03-10")

    assert s.top_products(start="2026-03-05") == [{"sku": "B-2", "units": 3}]
    assert s.top_products(end="2026-03-05") == [{"sku": "A-1", "units": 2}]
    assert s.top_products(start="2026-03-01", end="2026-03-01") == [
        {"sku": "A-1", "units": 2}
    ]


def test_top_products_rejects_bad_date_but_allows_start_after_end():
    s = _shop(FakeClock())
    with pytest.raises(ValidationError):
        s.top_products(start="2026-3-1")
    with pytest.raises(ValidationError):
        s.top_products(end=20260301)
    assert s.top_products(start="2026-03-10", end="2026-03-01") == []


# --- inventory_value ------------------------------------------------------

def test_inventory_value_sums_on_hand_times_price():
    s = Shop()
    s.add_product("A-1", "苹果", "10.00", "food")
    s.add_product("B-2", "书", "5.50", "books")
    s.receive("A-1", 3)
    s.receive("B-2", 2)
    assert s.inventory_value() == "41.00"


def test_inventory_value_includes_inactive_and_uses_current_price():
    s = Shop()
    s.add_product("A-1", "苹果", "10.00", "food")
    s.receive("A-1", 2)
    s.set_active("A-1", False)
    s.update_price("A-1", "12.00")
    assert s.inventory_value() == "24.00"
