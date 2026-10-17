import json
import os
from datetime import datetime

import pytest

from shopkit import Shop
from shopkit.errors import NotFoundError


def _build(shop):
    shop.add_product("A-1", "Apple", "10", "Food")
    shop.add_product("B-2", "Beer", "5", "Drink", active=False)
    shop.receive("A-1", 20)
    shop.adjust("A-1", -2, "damaged")
    shop.set_reorder_level("A-1", 5)
    shop.set_tier_price("A-1", 5, "8")
    shop.set_category_discount("food", 10)
    shop.set_tax_rate("food", "13")

    shop.add_coupon("USED", "fixed", "2")
    shop.add_coupon("FREE", "percent", 10, min_subtotal="5", expires="2026-12-31")

    # a delivered order
    o1 = shop.create_order("张三", [{"sku": "A-1", "qty": 2}], coupon="used")
    pricing = shop.place_order(o1)
    shop.pay(o1, pricing["pricing"]["total"])
    shop.ship(o1)
    shop.deliver(o1)

    # a placed order reserving stock
    o2 = shop.create_order("李四", [{"sku": "A-1", "qty": 3}])
    shop.place_order(o2)

    # a cancelled paid order with refund
    o3 = shop.create_order("王五", [{"sku": "A-1", "qty": 1}])
    pricing = shop.place_order(o3)
    shop.pay(o3, pricing["pricing"]["total"])
    shop.cancel(o3, "changed")

    # a draft
    shop.create_order("赵六", [], coupon="free")
    return ["A-1", "B-2"]


def _snapshot(shop, skus):
    return {
        "products": shop.list_products(),
        "stock": {sku: shop.stock(sku) for sku in skus},
        "logs": {sku: shop.stock_log(sku) for sku in skus},
        "low": shop.low_stock(),
        "coupons": {c: shop.get_coupon(c) for c in ("USED", "FREE")},
        "orders": shop.list_orders(),
        "inv": shop.inventory_value(),
        "report": shop.sales_report("2000-01-01", "2100-01-01"),
        "top": shop.top_products(limit=100),
    }


def test_save_load_roundtrip(shop, clock, tmp_path):
    skus = _build(shop)
    before = _snapshot(shop, skus)

    path = tmp_path / "state.json"
    shop.save(str(path))
    assert path.exists()

    loaded = Shop.load(str(path), clock=clock)
    after = _snapshot(loaded, skus)
    assert before == after


def test_save_leaves_no_temp_files(shop, tmp_path):
    _build(shop)
    path = tmp_path / "state.json"
    shop.save(str(path))
    leftovers = [p for p in os.listdir(tmp_path) if p.startswith(".shopkit-")]
    assert leftovers == []


def test_save_is_utf8_json(shop, tmp_path):
    _build(shop)
    path = tmp_path / "state.json"
    shop.save(str(path))
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    assert data["products"]["A-1"]["name"] == "Apple"
    assert data["orders"]  # orders persisted


def test_load_missing_file(shop, tmp_path):
    with pytest.raises(NotFoundError):
        Shop.load(str(tmp_path / "nope.json"))


def test_loaded_shop_uses_passed_clock(shop, clock, tmp_path):
    _build(shop)
    path = tmp_path / "state.json"
    shop.save(str(path))

    clock.set(datetime(2027, 1, 2, 8, 15, 0))
    loaded = Shop.load(str(path), clock=clock)
    order_id = loaded.create_order("new")
    assert loaded.get_order(order_id)["events"] == [
        {"at": "2027-01-02T08:15:00", "status": "draft"}
    ]


def test_loaded_coupon_usage_preserved(shop, clock, tmp_path):
    _build(shop)
    path = tmp_path / "state.json"
    shop.save(str(path))
    loaded = Shop.load(str(path), clock=clock)

    assert loaded.get_coupon("USED")["used_by"] == "O0001"
    # FREE coupon is on a draft order -> still unused
    assert loaded.get_coupon("FREE")["used_by"] is None


def test_loaded_order_numbering_continues(shop, clock, tmp_path):
    _build(shop)
    path = tmp_path / "state.json"
    shop.save(str(path))
    loaded = Shop.load(str(path), clock=clock)
    assert loaded.create_order("x") == "O0005"
