"""S12 订单验收测试：订单号、状态机、库存预留/释放/扣减、优惠券占用、价格快照。"""

import pytest

from shopkit import Shop
from shopkit.errors import (
    CouponError,
    NotFoundError,
    StateError,
    StockError,
    ValidationError,
)


def shop_with_products():
    """两个上架商品，各有 10 件库存。"""
    s = Shop()
    s.add_product("A-1", "苹果", "10.00", "food")
    s.add_product("B-2", "书", "5.00", "books")
    s.receive("A-1", 10)
    s.receive("B-2", 10)
    return s


# --- 订单号 ---------------------------------------------------------------

def test_order_numbers_start_at_0001_and_increment():
    s = shop_with_products()
    assert s.create_order("张三") == "O0001"
    assert s.create_order("李四") == "O0002"


def test_cancelled_order_number_is_not_reused():
    s = shop_with_products()
    oid = s.create_order("张三")
    s.cancel(oid, "不想要了")
    assert s.create_order("李四") == "O0002"


# --- create_order ---------------------------------------------------------

def test_create_order_returns_draft_with_event():
    s = shop_with_products()
    oid = s.create_order("张三")
    order = s.get_order(oid)
    assert order["id"] == oid
    assert order["status"] == "draft"
    assert order["items"] == []
    assert order["coupon"] is None
    assert order["pricing"] is None
    assert order["paid"] is None
    assert order["refund"] is None
    assert order["cancel_reason"] is None
    assert [e["status"] for e in order["events"]] == ["draft"]


def test_create_order_strips_customer_and_rejects_empty():
    s = shop_with_products()
    oid = s.create_order("  张三  ")
    assert s.get_order(oid)["customer"] == "张三"
    with pytest.raises(ValidationError):
        s.create_order("   ")
    with pytest.raises(ValidationError):
        s.create_order(123)


def test_create_order_rejects_bad_items():
    s = shop_with_products()
    with pytest.raises(ValidationError):
        s.create_order("张三", items="notalist")
    with pytest.raises(ValidationError):
        s.create_order("张三", items=[{"sku": "A-1"}])
    with pytest.raises(ValidationError):
        s.create_order("张三", items=[{"sku": "A-1", "qty": 1, "extra": 2}])
    with pytest.raises(ValidationError):
        s.create_order("张三", items=[{"sku": 123, "qty": 1}])
    with pytest.raises(ValidationError):
        s.create_order("张三", items=[{"sku": "A-1", "qty": 0}])
    with pytest.raises(ValidationError):
        s.create_order("张三", items=[{"sku": "A-1", "qty": True}])


def test_create_order_validates_sku():
    s = shop_with_products()
    with pytest.raises(NotFoundError):
        s.create_order("张三", items=[{"sku": "Z-9", "qty": 1}])
    s.set_active("A-1", False)
    with pytest.raises(ValidationError):
        s.create_order("张三", items=[{"sku": "A-1", "qty": 1}])


def test_create_order_merges_duplicate_skus():
    s = shop_with_products()
    oid = s.create_order(
        "张三",
        items=[{"sku": "A-1", "qty": 2}, {"sku": "A-1", "qty": 3}],
    )
    assert s.get_order(oid)["items"] == [{"sku": "A-1", "qty": 5}]


def test_create_order_stores_normalized_coupon():
    s = shop_with_products()
    s.add_coupon("SAVE10", "fixed", "5.00")
    oid = s.create_order("张三", coupon="  save10  ")
    assert s.get_order(oid)["coupon"] == "SAVE10"
    with pytest.raises(ValidationError):
        s.create_order("张三", coupon=5)


# --- add_item / remove_item / set_coupon ---------------------------------

def test_add_item_merges_and_appends():
    s = shop_with_products()
    oid = s.create_order("张三")
    s.add_item(oid, "A-1", 2)
    s.add_item(oid, "B-2", 1)
    s.add_item(oid, "A-1", 3)
    assert s.get_order(oid)["items"] == [
        {"sku": "A-1", "qty": 5},
        {"sku": "B-2", "qty": 1},
    ]


def test_add_item_validates_qty_and_sku():
    s = shop_with_products()
    oid = s.create_order("张三")
    with pytest.raises(ValidationError):
        s.add_item(oid, "A-1", 0)
    with pytest.raises(ValidationError):
        s.add_item(oid, "A-1", True)
    with pytest.raises(NotFoundError):
        s.add_item(oid, "Z-9", 1)
    s.set_active("A-1", False)
    with pytest.raises(ValidationError):
        s.add_item(oid, "A-1", 1)
    assert s.get_order(oid)["items"] == []


def test_remove_item_missing_sku_not_found():
    s = shop_with_products()
    oid = s.create_order("张三", items=[{"sku": "A-1", "qty": 1}])
    with pytest.raises(NotFoundError):
        s.remove_item(oid, "B-2")
    assert s.remove_item(oid, "A-1")["items"] == []


def test_set_coupon_and_clear():
    s = shop_with_products()
    s.add_coupon("SAVE10", "fixed", "5.00")
    oid = s.create_order("张三")
    assert s.set_coupon(oid, "save10")["coupon"] == "SAVE10"
    assert s.set_coupon(oid, None)["coupon"] is None


# --- place_order ----------------------------------------------------------

def test_place_order_requires_items():
    s = shop_with_products()
    oid = s.create_order("张三")
    with pytest.raises(ValidationError):
        s.place_order(oid)


def test_place_order_reserves_stock_and_sets_pricing():
    s = shop_with_products()
    oid = s.create_order("张三", items=[{"sku": "A-1", "qty": 2}])
    order = s.place_order(oid)
    assert order["status"] == "placed"
    assert order["pricing"]["lines"][0]["unit_price"] == "10.00"
    assert order["pricing"]["total"] == "20.00"
    assert s.stock("A-1") == {"on_hand": 10, "reserved": 2, "available": 8}
    assert [e["status"] for e in order["events"]] == ["draft", "placed"]


def test_place_order_insufficient_stock_is_atomic():
    s = Shop()
    s.add_product("A-1", "苹果", "10.00", "food")
    s.receive("A-1", 3)
    oid = s.create_order("张三", items=[{"sku": "A-1", "qty": 5}])
    with pytest.raises(StockError):
        s.place_order(oid)
    assert s.stock("A-1")["reserved"] == 0
    assert s.get_order(oid)["status"] == "draft"
    assert s.get_order(oid)["pricing"] is None


def test_place_order_rejects_inactive_product():
    s = shop_with_products()
    oid = s.create_order("张三", items=[{"sku": "A-1", "qty": 1}])
    s.set_active("A-1", False)
    with pytest.raises(ValidationError):
        s.place_order(oid)


def test_place_order_rejects_unavailable_coupon():
    s = shop_with_products()
    s.add_coupon("SAVE10", "fixed", "5.00", min_subtotal="50.00")
    oid = s.create_order(
        "张三", items=[{"sku": "A-1", "qty": 1}], coupon="SAVE10"
    )
    with pytest.raises(CouponError):
        s.place_order(oid)


def test_place_order_uses_coupon():
    s = shop_with_products()
    s.add_coupon("SAVE10", "fixed", "5.00")
    oid = s.create_order(
        "张三", items=[{"sku": "A-1", "qty": 1}], coupon="save10"
    )
    order = s.place_order(oid)
    assert order["coupon"] == "SAVE10"
    assert order["pricing"]["coupon_discount"] == "5.00"
    assert order["pricing"]["total"] == "5.00"
    assert s.get_coupon("SAVE10")["used_by"] == oid


def test_pricing_snapshot_immune_to_update_price():
    s = shop_with_products()
    oid = s.create_order("张三", items=[{"sku": "A-1", "qty": 2}])
    s.place_order(oid)
    s.update_price("A-1", "99.00")
    order = s.get_order(oid)
    assert order["pricing"]["lines"][0]["unit_price"] == "10.00"
    assert order["pricing"]["total"] == "20.00"


# --- pay / ship / deliver -------------------------------------------------

def test_pay_requires_exact_amount():
    s = shop_with_products()
    oid = s.create_order("张三", items=[{"sku": "A-1", "qty": 2}])
    s.place_order(oid)
    with pytest.raises(ValidationError):
        s.pay(oid, "19.99")
    with pytest.raises(ValidationError):
        s.pay(oid, "abc")
    order = s.pay(oid, "20.00")
    assert order["status"] == "paid"
    assert order["paid"] == "20.00"
    assert [e["status"] for e in order["events"]] == ["draft", "placed", "paid"]


def test_invalid_state_transitions_raise_state_error():
    s = shop_with_products()
    oid = s.create_order("张三", items=[{"sku": "A-1", "qty": 1}])
    with pytest.raises(StateError):
        s.pay(oid, "10.00")
    with pytest.raises(StateError):
        s.ship(oid)
    with pytest.raises(StateError):
        s.deliver(oid)

    s.place_order(oid)
    with pytest.raises(StateError):
        s.add_item(oid, "A-1", 1)
    with pytest.raises(StateError):
        s.remove_item(oid, "A-1")
    with pytest.raises(StateError):
        s.set_coupon(oid, None)
    with pytest.raises(StateError):
        s.place_order(oid)
    with pytest.raises(StateError):
        s.ship(oid)

    s.pay(oid, "10.00")
    with pytest.raises(StateError):
        s.pay(oid, "10.00")
    with pytest.raises(StateError):
        s.deliver(oid)

    s.ship(oid)
    with pytest.raises(StateError):
        s.ship(oid)

    order = s.deliver(oid)
    assert order["status"] == "delivered"
    with pytest.raises(StateError):
        s.cancel(oid, "太晚了")


def test_ship_consumes_stock_and_logs():
    s = shop_with_products()
    oid = s.create_order("张三", items=[{"sku": "A-1", "qty": 2}])
    s.place_order(oid)
    s.pay(oid, "20.00")
    order = s.ship(oid)
    assert order["status"] == "shipped"
    assert [e["status"] for e in order["events"]] == [
        "draft", "placed", "paid", "shipped"
    ]
    assert s.stock("A-1") == {"on_hand": 8, "reserved": 0, "available": 8}
    log = s.stock_log("A-1")
    assert log[-1]["change"] == -2
    assert log[-1]["reason"] == f"ship {oid}"


# --- cancel ---------------------------------------------------------------

def test_cancel_draft_and_reason_validation():
    s = shop_with_products()
    oid = s.create_order("张三", items=[{"sku": "A-1", "qty": 1}])
    with pytest.raises(ValidationError):
        s.cancel(oid, "   ")
    order = s.cancel(oid, "  不想要了  ")
    assert order["status"] == "cancelled"
    assert order["cancel_reason"] == "不想要了"
    assert order["refund"] is None
    assert s.stock("A-1")["reserved"] == 0


def test_cancel_placed_releases_stock_and_coupon():
    s = shop_with_products()
    s.add_coupon("SAVE5", "fixed", "5.00")
    oid = s.create_order(
        "张三", items=[{"sku": "A-1", "qty": 2}], coupon="SAVE5"
    )
    s.place_order(oid)
    assert s.stock("A-1")["reserved"] == 2
    order = s.cancel(oid, "改主意")
    assert order["status"] == "cancelled"
    assert order["refund"] is None
    assert s.stock("A-1")["reserved"] == 0
    assert s.get_coupon("SAVE5")["used_by"] is None


def test_cancel_paid_records_refund():
    s = shop_with_products()
    oid = s.create_order("张三", items=[{"sku": "A-1", "qty": 2}])
    s.place_order(oid)
    s.pay(oid, "20.00")
    order = s.cancel(oid, "退款")
    assert order["status"] == "cancelled"
    assert order["refund"] == "20.00"
    assert s.stock("A-1")["reserved"] == 0


# --- get_order / list_orders ---------------------------------------------

def test_get_order_and_unknown_order_not_found():
    s = shop_with_products()
    with pytest.raises(NotFoundError):
        s.get_order("O9999")
    with pytest.raises(NotFoundError):
        s.add_item("O9999", "A-1", 1)
    with pytest.raises(NotFoundError):
        s.place_order("O9999")
    with pytest.raises(NotFoundError):
        s.pay("O9999", "1.00")
    with pytest.raises(NotFoundError):
        s.ship("O9999")
    with pytest.raises(NotFoundError):
        s.deliver("O9999")
    with pytest.raises(NotFoundError):
        s.set_coupon("O9999", None)
    with pytest.raises(NotFoundError):
        s.cancel("O9999", "x")

    oid = s.create_order("张三", items=[{"sku": "A-1", "qty": 1}])
    order = s.get_order(oid)
    order["status"] = "hacked"
    assert s.get_order(oid)["status"] == "draft"


def test_list_orders_filters_sorted_and_validates_status():
    s = shop_with_products()
    o1 = s.create_order("张三", items=[{"sku": "A-1", "qty": 1}])
    o2 = s.create_order("李四", items=[{"sku": "B-2", "qty": 1}])
    s.place_order(o2)

    assert [o["id"] for o in s.list_orders()] == [o1, o2]
    assert [o["id"] for o in s.list_orders(status="placed")] == [o2]
    assert [o["id"] for o in s.list_orders(status="draft")] == [o1]
    assert [o["id"] for o in s.list_orders(customer="  张三  ")] == [o1]
    assert s.list_orders(customer="王五") == []

    with pytest.raises(ValidationError):
        s.list_orders(status="unknown")
