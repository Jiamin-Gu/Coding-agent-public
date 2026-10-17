from datetime import datetime

import pytest

from shopkit.errors import ValidationError


def _setup_products(shop):
    shop.add_product("A-1", "A", "10", "food")
    shop.add_product("B-2", "B", "5", "drink")
    shop.receive("A-1", 100)
    shop.receive("B-2", 100)
    shop.set_tax_rate("food", "10")


def _ship(shop, clock, day, items):
    clock.set(datetime(day.year, day.month, day.day, 12, 0, 0))
    order_id = shop.create_order("c", items)
    pricing = shop.place_order(order_id)
    shop.pay(order_id, pricing["pricing"]["total"])
    shop.ship(order_id)
    return order_id


def test_sales_report(shop, clock):
    _setup_products(shop)
    _ship(shop, clock, datetime(2026, 3, 5), [{"sku": "A-1", "qty": 2}])
    _ship(
        shop,
        clock,
        datetime(2026, 3, 10),
        [{"sku": "A-1", "qty": 1}, {"sku": "B-2", "qty": 3}],
    )

    report = shop.sales_report("2026-03-01", "2026-03-31")
    assert report == {
        "orders": 2,
        "units": 6,
        "subtotal": "45.00",
        "coupon_discount": "0.00",
        "tax": "3.00",
        "revenue": "48.00",
        "by_category": [
            {"category": "food", "units": 3, "net": "30.00"},
            {"category": "drink", "units": 3, "net": "15.00"},
        ],
    }


def test_sales_report_date_filter(shop, clock):
    _setup_products(shop)
    _ship(shop, clock, datetime(2026, 3, 5), [{"sku": "A-1", "qty": 2}])
    _ship(shop, clock, datetime(2026, 3, 10), [{"sku": "A-1", "qty": 1}])

    report = shop.sales_report("2026-03-06", "2026-03-31")
    assert report["orders"] == 1
    assert report["units"] == 1


def test_sales_report_excludes_unshipped(shop, clock):
    _setup_products(shop)
    order_id = shop.create_order("c", [{"sku": "A-1", "qty": 2}])
    shop.place_order(order_id)  # placed, not shipped
    report = shop.sales_report("2026-03-01", "2026-03-31")
    assert report["orders"] == 0
    assert report["revenue"] == "0.00"
    assert report["by_category"] == []


def test_sales_report_date_validation(shop):
    with pytest.raises(ValidationError):
        shop.sales_report("2026-3-1", "2026-03-31")
    with pytest.raises(ValidationError):
        shop.sales_report("2026-03-31", "2026-03-01")
    with pytest.raises(ValidationError):
        shop.sales_report("not-a-date", "2026-03-01")


def test_top_products(shop, clock):
    _setup_products(shop)
    _ship(
        shop,
        clock,
        datetime(2026, 3, 5),
        [{"sku": "A-1", "qty": 2}, {"sku": "B-2", "qty": 5}],
    )
    _ship(shop, clock, datetime(2026, 3, 10), [{"sku": "A-1", "qty": 4}])

    assert shop.top_products() == [
        {"sku": "A-1", "units": 6},
        {"sku": "B-2", "units": 5},
    ]
    assert shop.top_products(limit=1) == [{"sku": "A-1", "units": 6}]
    assert shop.top_products(start="2026-03-06") == [{"sku": "A-1", "units": 4}]
    assert shop.top_products(end="2026-03-06") == [
        {"sku": "B-2", "units": 5},
        {"sku": "A-1", "units": 2},
    ]


def test_top_products_ties_sorted_by_sku(shop, clock):
    _setup_products(shop)
    _ship(
        shop,
        clock,
        datetime(2026, 3, 5),
        [{"sku": "B-2", "qty": 2}, {"sku": "A-1", "qty": 2}],
    )
    assert shop.top_products() == [
        {"sku": "A-1", "units": 2},
        {"sku": "B-2", "units": 2},
    ]


def test_top_products_limit_validation(shop):
    with pytest.raises(ValidationError):
        shop.top_products(limit=0)
    with pytest.raises(ValidationError):
        shop.top_products(limit=True)
    with pytest.raises(ValidationError):
        shop.top_products(limit="5")


def test_inventory_value(shop):
    shop.add_product("A-1", "A", "10.50", "food")
    shop.add_product("B-2", "B", "2", "food", active=False)
    shop.receive("A-1", 4)
    shop.receive("B-2", 3)
    assert shop.inventory_value() == "48.00"
