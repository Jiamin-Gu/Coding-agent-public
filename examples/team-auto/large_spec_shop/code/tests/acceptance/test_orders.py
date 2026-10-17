import pytest

from shopkit import Shop
from shopkit.errors import (
    CouponError,
    NotFoundError,
    StateError,
    StockError,
    ValidationError,
)


def build(shop):
    shop.add_product("FOOD-1", "Bread", "10.00", "food")
    shop.add_product("TOY-1", "Ball", "20.00", "toys")
    shop.set_category_discount("food", 10)
    shop.set_tax_rate("food", 5)
    shop.set_tax_rate("toys", 10)
    shop.add_coupon("FIX5", "fixed", "5", min_subtotal="20")
    shop.add_coupon("SAVE10", "percent", 10)
    shop.receive("FOOD-1", 100)
    shop.receive("TOY-1", 100)
    return shop


def test_full_order_flow(shop, clock):
    build(shop)
    oid = shop.create_order("  张三 ", [{"sku": "FOOD-1", "qty": 3}, {"sku": "TOY-1", "qty": 1}], "fix5")
    assert oid == "O0001"
    o = shop.get_order(oid)
    assert o["customer"] == "张三"
    assert o["status"] == "draft"
    assert o["items"] == [{"sku": "FOOD-1", "qty": 3}, {"sku": "TOY-1", "qty": 1}]
    assert o["coupon"] == "FIX5"
    assert o["pricing"] is None
    assert o["paid"] is None
    assert o["refund"] is None
    assert o["events"] == [{"at": "2026-03-01T09:30:00", "status": "draft"}]

    o = shop.place_order(oid)
    assert o["status"] == "placed"
    pr = o["pricing"]
    assert pr["subtotal"] == "47.00"
    assert pr["coupon_discount"] == "5.00"
    assert pr["lines"][0]["net"] == "27.00"
    assert pr["lines"][0]["coupon_share"] == "2.87"
    assert pr["lines"][1]["net"] == "20.00"
    assert pr["lines"][1]["coupon_share"] == "2.13"
    assert pr["lines"][0]["tax"] == "1.21"
    assert pr["lines"][1]["tax"] == "1.79"
    assert pr["tax"] == "3.00"
    assert pr["total"] == "45.00"
    assert shop.stock("FOOD-1") == {"on_hand": 100, "reserved": 3, "available": 97}
    assert shop.stock("TOY-1") == {"on_hand": 100, "reserved": 1, "available": 99}
    assert shop.get_coupon("FIX5")["used_by"] == "O0001"

    o = shop.pay(oid, "45")
    assert o["status"] == "paid"
    assert o["paid"] == "45.00"

    o = shop.ship(oid)
    assert o["status"] == "shipped"
    assert shop.stock("FOOD-1") == {"on_hand": 97, "reserved": 0, "available": 97}
    assert shop.stock("TOY-1") == {"on_hand": 99, "reserved": 0, "available": 99}
    assert shop.stock_log("FOOD-1")[-1] == {
        "at": "2026-03-01T09:30:00",
        "change": -3,
        "reason": "ship O0001",
    }

    o = shop.deliver(oid)
    assert o["status"] == "delivered"
    assert [e["status"] for e in o["events"]] == [
        "draft",
        "placed",
        "paid",
        "shipped",
        "delivered",
    ]


def test_update_price_does_not_affect_placed(shop):
    build(shop)
    oid = shop.create_order("c", [{"sku": "FOOD-1", "qty": 1}])
    shop.place_order(oid)
    shop.update_price("FOOD-1", "999.00")
    assert shop.get_order(oid)["pricing"]["lines"][0]["unit_price"] == "10.00"
    assert shop.get_order(oid)["pricing"]["total"] == "9.45"


def test_add_remove_item(shop):
    build(shop)
    oid = shop.create_order("c")
    shop.add_item(oid, "FOOD-1", 1)
    shop.add_item(oid, "FOOD-1", 2)
    shop.add_item(oid, "TOY-1", 1)
    assert shop.get_order(oid)["items"] == [
        {"sku": "FOOD-1", "qty": 3},
        {"sku": "TOY-1", "qty": 1},
    ]
    shop.remove_item(oid, "FOOD-1")
    assert shop.get_order(oid)["items"] == [{"sku": "TOY-1", "qty": 1}]
    with pytest.raises(NotFoundError):
        shop.remove_item(oid, "FOOD-1")


def test_add_item_on_placed_is_state_error(shop):
    build(shop)
    oid = shop.create_order("c", [{"sku": "FOOD-1", "qty": 1}])
    shop.place_order(oid)
    with pytest.raises(StateError):
        shop.add_item(oid, "TOY-1", 1)


def test_set_coupon(shop):
    build(shop)
    oid = shop.create_order("c", [{"sku": "FOOD-1", "qty": 1}])
    assert shop.set_coupon(oid, " save10 ")["coupon"] == "SAVE10"
    assert shop.set_coupon(oid, None)["coupon"] is None


def test_place_empty_order(shop):
    build(shop)
    oid = shop.create_order("c")
    with pytest.raises(ValidationError):
        shop.place_order(oid)


def test_place_insufficient_stock_is_atomic(shop):
    build(shop)
    oid = shop.create_order("c", [{"sku": "FOOD-1", "qty": 1000}])
    with pytest.raises(StockError):
        shop.place_order(oid)
    assert shop.stock("FOOD-1") == {"on_hand": 100, "reserved": 0, "available": 100}
    assert shop.get_order(oid)["status"] == "draft"
    assert shop.get_coupon("FIX5")["used_by"] is None


def test_pay_wrong_amount(shop):
    build(shop)
    oid = shop.create_order("c", [{"sku": "FOOD-1", "qty": 1}])
    shop.place_order(oid)
    with pytest.raises(ValidationError):
        shop.pay(oid, "1.00")


def test_pay_draft_is_state_error(shop):
    build(shop)
    oid = shop.create_order("c", [{"sku": "FOOD-1", "qty": 1}])
    with pytest.raises(StateError):
        shop.pay(oid, "9.45")


def test_cancel_placed_releases_and_coupon(shop):
    build(shop)
    oid = shop.create_order("c", [{"sku": "FOOD-1", "qty": 3}], "SAVE10")
    shop.place_order(oid)
    shop.pay(oid, "25.52")
    o = shop.cancel(oid, "  客户取消  ")
    assert o["status"] == "cancelled"
    assert o["cancel_reason"] == "客户取消"
    assert o["refund"] == "25.52"
    assert shop.stock("FOOD-1") == {"on_hand": 100, "reserved": 0, "available": 100}
    assert shop.get_coupon("SAVE10")["used_by"] is None


def test_cancel_draft_no_refund(shop):
    build(shop)
    oid = shop.create_order("c", [{"sku": "FOOD-1", "qty": 1}])
    o = shop.cancel(oid, "reason")
    assert o["refund"] is None
    assert o["status"] == "cancelled"


def test_cancel_delivered_is_state_error(shop):
    build(shop)
    oid = shop.create_order("c", [{"sku": "FOOD-1", "qty": 1}])
    shop.place_order(oid)
    shop.pay(oid, "9.45")
    shop.ship(oid)
    shop.deliver(oid)
    with pytest.raises(StateError):
        shop.cancel(oid, "x")


def test_cancel_bad_reason(shop):
    build(shop)
    oid = shop.create_order("c", [{"sku": "FOOD-1", "qty": 1}])
    with pytest.raises(ValidationError):
        shop.cancel(oid, "   ")


def test_coupon_single_use(shop):
    build(shop)
    o1 = shop.create_order("c", [{"sku": "FOOD-1", "qty": 3}], "FIX5")
    shop.place_order(o1)
    o2 = shop.create_order("c", [{"sku": "FOOD-1", "qty": 3}], "FIX5")
    with pytest.raises(CouponError):
        shop.place_order(o2)


def test_order_ids_increment(shop):
    build(shop)
    assert shop.create_order("a") == "O0001"
    assert shop.create_order("b") == "O0002"
    shop.cancel("O0002", "x")
    assert shop.create_order("c") == "O0003"


def test_list_orders(shop):
    build(shop)
    shop.create_order("Alice")
    shop.create_order("Bob")
    oid = shop.create_order("Alice")
    shop.cancel(oid, "x")
    assert [o["id"] for o in shop.list_orders()] == ["O0001", "O0002", "O0003"]
    assert [o["id"] for o in shop.list_orders(customer=" Alice ")] == ["O0001", "O0003"]
    assert [o["id"] for o in shop.list_orders(status="cancelled")] == ["O0003"]
    with pytest.raises(ValidationError):
        shop.list_orders(status="bogus")


def test_missing_order(shop):
    build(shop)
    with pytest.raises(NotFoundError):
        shop.get_order("O9999")
    with pytest.raises(NotFoundError):
        shop.place_order("O9999")


def test_ship_wrong_state(shop):
    build(shop)
    oid = shop.create_order("c", [{"sku": "FOOD-1", "qty": 1}])
    shop.place_order(oid)
    with pytest.raises(StateError):
        shop.ship(oid)
