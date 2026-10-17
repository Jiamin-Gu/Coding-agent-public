import json

import pytest

from shopkit import Shop
from shopkit.errors import NotFoundError


def build(shop):
    shop.add_product("FOOD-1", "Bread", "10.00", "food")
    shop.add_product("TOY-1", "Ball", "20.00", "toys", active=False)
    shop.set_category_discount("food", 10)
    shop.set_tax_rate("food", 5)
    shop.set_tier_price("FOOD-1", 5, "8.00")
    shop.add_coupon("FIX5", "fixed", "5", min_subtotal="20", expires="2026-12-31")
    shop.receive("FOOD-1", 100)
    shop.receive("TOY-1", 50)
    shop.set_reorder_level("FOOD-1", 3)
    shop.adjust("TOY-1", -2, "shrink")

    oid = shop.create_order("张三", [{"sku": "FOOD-1", "qty": 3}], "FIX5")
    shop.place_order(oid)
    shop.pay(oid, shop.get_order(oid)["pricing"]["total"])
    shop.ship(oid)
    shop.set_active("TOY-1", True)

    o2 = shop.create_order("李四", [{"sku": "FOOD-1", "qty": 1}])
    shop.cancel(o2, "changed mind")
    return shop


def test_save_and_load_roundtrip(tmp_path, clock):
    shop = build(Shop(clock=clock))
    path = tmp_path / "state.json"
    shop.save(str(path))
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)

    loaded = Shop.load(str(path), clock=clock)
    assert loaded.list_products() == shop.list_products()
    assert loaded.stock("FOOD-1") == shop.stock("FOOD-1")
    assert loaded.stock("TOY-1") == shop.stock("TOY-1")
    assert loaded.stock_log("FOOD-1") == shop.stock_log("FOOD-1")
    assert loaded.get_coupon("FIX5") == shop.get_coupon("FIX5")
    assert loaded.get_order("O0001") == shop.get_order("O0001")
    assert loaded.get_order("O0002") == shop.get_order("O0002")
    assert loaded.low_stock() == shop.low_stock()

    # pricing rules survive
    assert loaded.quote([{"sku": "FOOD-1", "qty": 5}]) == shop.quote(
        [{"sku": "FOOD-1", "qty": 5}]
    )
    # order sequence survives (cancelled numbers are not reused)
    assert loaded.create_order("王五") == "O0003"


def test_load_missing_file(tmp_path, clock):
    with pytest.raises(NotFoundError):
        Shop.load(str(tmp_path / "missing.json"), clock=clock)
