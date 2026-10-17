"""S14 持久化验收测试：save/load 完整恢复、原子写、缺失文件报错。"""

import json
from datetime import datetime

import pytest

from shopkit import Shop
from shopkit.errors import NotFoundError


class FakeClock:
    """可手动设置当前时间的时钟。"""

    def __init__(self, value=None):
        self.value = value or datetime(2026, 1, 1, 9, 0, 0)

    def __call__(self):
        return self.value


def test_save_writes_utf8_json(tmp_path):
    s = Shop()
    s.add_product("A-1", "苹果", "10.00", "food")
    path = tmp_path / "shop.json"
    s.save(str(path))

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert data["products"]["A-1"]["price"] == "10.00"
    assert data["next_no"] == 1


def test_save_leaves_no_temp_files(tmp_path):
    s = Shop()
    s.add_product("A-1", "苹果", "10.00", "food")
    path = tmp_path / "shop.json"
    s.save(str(path))
    assert [p.name for p in tmp_path.iterdir()] == ["shop.json"]


def test_load_missing_file_not_found(tmp_path):
    with pytest.raises(NotFoundError):
        Shop.load(str(tmp_path / "missing.json"))


def test_roundtrip_restores_catalog_and_stock(tmp_path):
    s = Shop()
    s.add_product("A-1", "苹果", "10.00", "food")
    s.add_product("B-2", "书", "5.00", "Books")
    s.receive("A-1", 5)
    s.adjust("A-1", -2, "盘点")
    s.set_reorder_level("A-1", 3)
    path = tmp_path / "shop.json"
    s.save(str(path))

    r = Shop.load(str(path))
    assert r.get_product("A-1") == {
        "sku": "A-1",
        "name": "苹果",
        "price": "10.00",
        "category": "food",
        "active": True,
    }
    assert r.get_product("B-2")["category"] == "books"
    assert r.stock("A-1") == {"on_hand": 3, "reserved": 0, "available": 3}

    log = r.stock_log("A-1")
    assert len(log) == 2
    assert [e["change"] for e in log] == [5, -2]
    assert [e["reason"] for e in log] == ["receive", "盘点"]
    assert r.low_stock() == [
        {"sku": "A-1", "available": 3, "reorder_level": 3}
    ]


def test_roundtrip_restores_pricing_config(tmp_path):
    s = Shop()
    s.add_product("A-1", "苹果", "10.00", "food")
    s.set_tier_price("A-1", 3, "8.00")
    s.set_category_discount("food", 10)
    s.set_tax_rate("food", "5")
    path = tmp_path / "shop.json"
    s.save(str(path))

    r = Shop.load(str(path))
    quote = r.quote([{"sku": "A-1", "qty": 3}])
    assert quote["lines"][0]["unit_price"] == "8.00"
    assert quote["lines"][0]["discount"] == "2.40"
    assert quote["lines"][0]["net"] == "21.60"
    assert quote["total"] == "22.68"


def test_roundtrip_restores_coupons_and_used_by(tmp_path):
    s = Shop()
    s.add_product("A-1", "苹果", "10.00", "food")
    s.receive("A-1", 10)
    s.add_coupon(
        "SAVE5", "fixed", "5.00", min_subtotal="5.00", expires="2030-12-31"
    )
    oid = s.create_order(
        "张三", [{"sku": "A-1", "qty": 1}], coupon="SAVE5"
    )
    s.place_order(oid)
    path = tmp_path / "shop.json"
    s.save(str(path))

    r = Shop.load(str(path))
    coupon = r.get_coupon("SAVE5")
    assert coupon["kind"] == "fixed"
    assert coupon["value"] == "5.00"
    assert coupon["min_subtotal"] == "5.00"
    assert coupon["expires"] == "2030-12-31"
    assert coupon["used_by"] == oid


def test_roundtrip_restores_orders_and_next_no(tmp_path):
    s = Shop()
    s.add_product("A-1", "苹果", "10.00", "food")
    s.receive("A-1", 10)
    o1 = s.create_order("张三", [{"sku": "A-1", "qty": 1}])
    s.place_order(o1)
    s.pay(o1, "10.00")
    s.ship(o1)
    s.deliver(o1)
    o2 = s.create_order("李四", [{"sku": "A-1", "qty": 2}])
    s.place_order(o2)
    s.pay(o2, "20.00")
    s.cancel(o2, "退款")
    path = tmp_path / "shop.json"
    s.save(str(path))

    r = Shop.load(str(path))
    assert r.get_order(o1) == s.get_order(o1)
    assert r.get_order(o2) == s.get_order(o2)
    assert r.get_order(o1)["pricing"]["total"] == "10.00"
    assert r.get_order(o2)["refund"] == "20.00"
    assert [e["status"] for e in r.get_order(o1)["events"]] == [
        "draft", "placed", "paid", "shipped", "delivered"
    ]
    # 订单号不回收，load 后继续递增
    assert r.create_order("王五") == "O0003"


def test_load_restores_reserved_stock(tmp_path):
    s = Shop()
    s.add_product("A-1", "苹果", "10.00", "food")
    s.receive("A-1", 10)
    oid = s.create_order("张三", [{"sku": "A-1", "qty": 4}])
    s.place_order(oid)
    path = tmp_path / "shop.json"
    s.save(str(path))

    r = Shop.load(str(path))
    assert r.stock("A-1") == {"on_hand": 10, "reserved": 4, "available": 6}
    assert r.get_order(oid)["status"] == "placed"


def test_save_serializes_coupon_value_types(tmp_path):
    s = Shop()
    s.add_coupon("FIX5", "fixed", "5.00")
    s.add_coupon("PCT10", "percent", 10)
    path = tmp_path / "shop.json"
    s.save(str(path))

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["coupons"]["FIX5"]["value"] == "5.00"
    assert data["coupons"]["PCT10"]["value"] == 10

    r = Shop.load(str(path))
    assert r.get_coupon("FIX5")["value"] == "5.00"
    assert r.get_coupon("PCT10")["value"] == 10


def test_load_uses_given_clock(tmp_path):
    s = Shop()
    s.add_product("A-1", "苹果", "10.00", "food")
    path = tmp_path / "shop.json"
    s.save(str(path))

    clock = FakeClock(datetime(2026, 1, 1, 9, 0, 0))
    r = Shop.load(str(path), clock=clock)
    oid = r.create_order("张三")
    assert r.get_order(oid)["events"][0]["at"] == "2026-01-01T09:00:00"
