from datetime import datetime

import pytest

from shopkit import Shop
from shopkit.errors import ValidationError


def build(shop):
    shop.add_product("FOOD-1", "Bread", "10.00", "food")
    shop.add_product("TOY-1", "Ball", "20.00", "toys")
    shop.set_category_discount("food", 10)
    shop.set_tax_rate("food", 5)
    shop.set_tax_rate("toys", 10)
    shop.add_coupon("FIX5", "fixed", "5", min_subtotal="20")
    shop.receive("FOOD-1", 100)
    shop.receive("TOY-1", 100)
    return shop


def ship_order(shop, items, coupon=None):
    oid = shop.create_order("c", items, coupon)
    shop.place_order(oid)
    total = shop.get_order(oid)["pricing"]["total"]
    shop.pay(oid, total)
    shop.ship(oid)
    return oid


def test_sales_report(shop):
    build(shop)
    ship_order(shop, [{"sku": "FOOD-1", "qty": 3}, {"sku": "TOY-1", "qty": 1}], "FIX5")
    r = shop.sales_report("2026-03-01", "2026-03-01")
    assert r == {
        "orders": 1,
        "units": 4,
        "subtotal": "47.00",
        "coupon_discount": "5.00",
        "tax": "3.00",
        "revenue": "45.00",
        "by_category": [
            {"category": "food", "units": 3, "net": "27.00"},
            {"category": "toys", "units": 1, "net": "20.00"},
        ],
    }


def test_top_products(shop):
    build(shop)
    ship_order(shop, [{"sku": "FOOD-1", "qty": 3}, {"sku": "TOY-1", "qty": 1}])
    assert shop.top_products() == [
        {"sku": "FOOD-1", "units": 3},
        {"sku": "TOY-1", "units": 1},
    ]
    assert shop.top_products(limit=1) == [{"sku": "FOOD-1", "units": 3}]


def test_reports_only_count_shipped(shop):
    build(shop)
    shop.create_order("c", [{"sku": "FOOD-1", "qty": 1}])
    shop.place_order("O0001")  # placed but not shipped
    r = shop.sales_report("2026-03-01", "2026-03-01")
    assert r["orders"] == 0
    assert r["revenue"] == "0.00"
    assert r["by_category"] == []
    assert shop.top_products() == []


def test_report_date_filter(clock, shop):
    build(shop)
    ship_order(shop, [{"sku": "FOOD-1", "qty": 1}])
    clock.set(datetime(2026, 4, 1, 9, 0, 0))
    ship_order(shop, [{"sku": "FOOD-1", "qty": 2}])
    assert shop.sales_report("2026-03-01", "2026-03-31")["units"] == 1
    assert shop.sales_report("2026-04-01", "2026-04-30")["units"] == 2
    assert shop.sales_report("2026-03-01", "2026-04-30")["orders"] == 2
    assert shop.top_products(start="2026-04-01") == [{"sku": "FOOD-1", "units": 2}]
    assert shop.top_products(end="2026-03-31") == [{"sku": "FOOD-1", "units": 1}]


def test_report_validation(shop):
    with pytest.raises(ValidationError):
        shop.sales_report("2026-03-02", "2026-03-01")
    with pytest.raises(ValidationError):
        shop.sales_report("2026-3-01", "2026-03-01")
    with pytest.raises(ValidationError):
        shop.top_products(limit=0)
    with pytest.raises(ValidationError):
        shop.top_products(limit=True)


def test_inventory_value(shop):
    build(shop)
    assert shop.inventory_value() == "3000.00"
    ship_order(shop, [{"sku": "FOOD-1", "qty": 3}, {"sku": "TOY-1", "qty": 1}])
    assert shop.inventory_value() == "2950.00"
