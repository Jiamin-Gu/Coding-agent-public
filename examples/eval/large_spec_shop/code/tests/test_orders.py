import pytest

from shopkit.errors import NotFoundError, StateError, StockError, ValidationError


def _prepare(shop, price="10", qty=10):
    shop.add_product("A-1", "A", price, "food")
    shop.receive("A-1", qty)


def test_create_order_numbering(shop):
    _prepare(shop)
    assert shop.create_order("张三") == "O0001"
    assert shop.create_order("李四") == "O0002"


def test_create_order_requires_customer(shop):
    with pytest.raises(ValidationError):
        shop.create_order("   ")
    with pytest.raises(ValidationError):
        shop.create_order(5)


def test_create_order_with_items(shop):
    _prepare(shop)
    order_id = shop.create_order("张三", [{"sku": "A-1", "qty": 2}])
    order = shop.get_order(order_id)
    assert order["customer"] == "张三"
    assert order["status"] == "draft"
    assert order["items"] == [{"sku": "A-1", "qty": 2}]
    assert order["pricing"] is None
    assert order["paid"] is None
    assert order["refund"] is None
    assert order["cancel_reason"] is None
    assert order["coupon"] is None
    assert order["events"] == [{"at": "2026-03-01T09:30:00", "status": "draft"}]


def test_create_order_empty_allowed(shop):
    assert shop.create_order("c", []) == "O0001"


def test_create_order_unknown_sku(shop):
    with pytest.raises(NotFoundError):
        shop.create_order("c", [{"sku": "NOPE", "qty": 1}])


def test_create_order_inactive(shop):
    shop.add_product("A-1", "A", "10", "food", active=False)
    with pytest.raises(ValidationError):
        shop.create_order("c", [{"sku": "A-1", "qty": 1}])


def test_create_order_merges_items(shop):
    _prepare(shop)
    order_id = shop.create_order(
        "c", [{"sku": "A-1", "qty": 1}, {"sku": "A-1", "qty": 2}]
    )
    assert shop.get_order(order_id)["items"] == [{"sku": "A-1", "qty": 3}]


def test_add_item(shop):
    _prepare(shop)
    order_id = shop.create_order("c")
    shop.add_item(order_id, "A-1", 2)
    result = shop.add_item(order_id, "A-1", 3)
    assert result["items"] == [{"sku": "A-1", "qty": 5}]


def test_add_item_validation(shop):
    _prepare(shop)
    order_id = shop.create_order("c")
    with pytest.raises(ValidationError):
        shop.add_item(order_id, "A-1", 0)
    with pytest.raises(ValidationError):
        shop.add_item(order_id, "A-1", True)
    with pytest.raises(NotFoundError):
        shop.add_item(order_id, "NOPE", 1)
    with pytest.raises(NotFoundError):
        shop.add_item("O9999", "A-1", 1)


def test_remove_item(shop):
    _prepare(shop)
    order_id = shop.create_order("c", [{"sku": "A-1", "qty": 2}])
    result = shop.remove_item(order_id, "A-1")
    assert result["items"] == []
    with pytest.raises(NotFoundError):
        shop.remove_item(order_id, "A-1")


def test_set_coupon(shop):
    _prepare(shop)
    shop.add_coupon("SAVE", "fixed", "2")
    order_id = shop.create_order("c", [{"sku": "A-1", "qty": 1}])
    result = shop.set_coupon(order_id, "save")
    assert result["coupon"] == "SAVE"
    assert shop.set_coupon(order_id, None)["coupon"] is None


def test_place_order(shop):
    _prepare(shop)
    order_id = shop.create_order("c", [{"sku": "A-1", "qty": 3}])
    result = shop.place_order(order_id)
    assert result["status"] == "placed"
    assert result["pricing"]["total"] == "30.00"
    assert shop.stock("A-1")["reserved"] == 3
    assert [e["status"] for e in result["events"]] == ["draft", "placed"]


def test_place_order_empty(shop):
    order_id = shop.create_order("c")
    with pytest.raises(ValidationError):
        shop.place_order(order_id)


def test_place_order_insufficient_stock_atomic(shop):
    _prepare(shop, qty=2)
    order_id = shop.create_order("c", [{"sku": "A-1", "qty": 5}])
    with pytest.raises(StockError):
        shop.place_order(order_id)
    order = shop.get_order(order_id)
    assert order["status"] == "draft"
    assert order["pricing"] is None
    assert shop.stock("A-1")["reserved"] == 0


def test_placed_pricing_is_snapshot(shop):
    _prepare(shop)
    order_id = shop.create_order("c", [{"sku": "A-1", "qty": 3}])
    shop.place_order(order_id)
    shop.update_price("A-1", "20")
    order = shop.get_order(order_id)
    assert order["pricing"]["lines"][0]["unit_price"] == "10.00"
    assert order["pricing"]["total"] == "30.00"


def test_place_order_coupon_occupied(shop):
    _prepare(shop)
    shop.add_coupon("SAVE", "fixed", "2")
    order_id = shop.create_order("c", [{"sku": "A-1", "qty": 3}], coupon="save")
    result = shop.place_order(order_id)
    assert result["pricing"]["coupon_discount"] == "2.00"
    assert shop.get_coupon("SAVE")["used_by"] == order_id


def test_place_order_only_draft(shop):
    _prepare(shop)
    order_id = shop.create_order("c", [{"sku": "A-1", "qty": 1}])
    shop.place_order(order_id)
    with pytest.raises(StateError):
        shop.place_order(order_id)
    with pytest.raises(StateError):
        shop.add_item(order_id, "A-1", 1)
    with pytest.raises(StateError):
        shop.remove_item(order_id, "A-1")
    with pytest.raises(StateError):
        shop.set_coupon(order_id, None)


def test_pay(shop):
    _prepare(shop)
    order_id = shop.create_order("c", [{"sku": "A-1", "qty": 3}])
    shop.place_order(order_id)
    result = shop.pay(order_id, "30")
    assert result["status"] == "paid"
    assert result["paid"] == "30.00"


def test_pay_wrong_amount(shop):
    _prepare(shop)
    order_id = shop.create_order("c", [{"sku": "A-1", "qty": 3}])
    shop.place_order(order_id)
    with pytest.raises(ValidationError):
        shop.pay(order_id, "29.99")
    assert shop.get_order(order_id)["status"] == "placed"


def test_pay_requires_placed(shop):
    _prepare(shop)
    order_id = shop.create_order("c", [{"sku": "A-1", "qty": 1}])
    with pytest.raises(StateError):
        shop.pay(order_id, "10")


def test_ship(shop):
    _prepare(shop)
    order_id = shop.create_order("c", [{"sku": "A-1", "qty": 3}])
    shop.place_order(order_id)
    shop.pay(order_id, "30")
    result = shop.ship(order_id)
    assert result["status"] == "shipped"
    assert shop.stock("A-1") == {"on_hand": 7, "reserved": 0, "available": 7}
    log = shop.stock_log("A-1")
    assert log[-1] == {
        "at": "2026-03-01T09:30:00",
        "change": -3,
        "reason": "ship O0001",
    }


def test_ship_requires_paid(shop):
    _prepare(shop)
    order_id = shop.create_order("c", [{"sku": "A-1", "qty": 1}])
    shop.place_order(order_id)
    with pytest.raises(StateError):
        shop.ship(order_id)


def test_deliver(shop):
    _prepare(shop)
    order_id = shop.create_order("c", [{"sku": "A-1", "qty": 1}])
    shop.place_order(order_id)
    shop.pay(order_id, "10")
    shop.ship(order_id)
    result = shop.deliver(order_id)
    assert result["status"] == "delivered"
    assert [e["status"] for e in result["events"]] == [
        "draft",
        "placed",
        "paid",
        "shipped",
        "delivered",
    ]


def test_cancel_draft(shop):
    _prepare(shop)
    order_id = shop.create_order("c", [{"sku": "A-1", "qty": 1}])
    result = shop.cancel(order_id, "  no thanks ")
    assert result["status"] == "cancelled"
    assert result["cancel_reason"] == "no thanks"
    assert result["refund"] is None


def test_cancel_placed_releases_reservation(shop):
    _prepare(shop)
    shop.add_coupon("SAVE", "fixed", "2")
    order_id = shop.create_order("c", [{"sku": "A-1", "qty": 3}], coupon="save")
    shop.place_order(order_id)
    assert shop.stock("A-1")["reserved"] == 3
    shop.cancel(order_id, "x")
    assert shop.stock("A-1")["reserved"] == 0
    assert shop.get_coupon("SAVE")["used_by"] is None


def test_cancel_paid_records_refund(shop):
    _prepare(shop)
    order_id = shop.create_order("c", [{"sku": "A-1", "qty": 3}])
    shop.place_order(order_id)
    shop.pay(order_id, "30")
    result = shop.cancel(order_id, "x")
    assert result["refund"] == "30.00"
    assert shop.stock("A-1")["reserved"] == 0


def test_cancel_bad_reason(shop):
    _prepare(shop)
    order_id = shop.create_order("c")
    with pytest.raises(ValidationError):
        shop.cancel(order_id, "   ")


def test_cancel_shipped_not_allowed(shop):
    _prepare(shop)
    order_id = shop.create_order("c", [{"sku": "A-1", "qty": 1}])
    shop.place_order(order_id)
    shop.pay(order_id, "10")
    shop.ship(order_id)
    with pytest.raises(StateError):
        shop.cancel(order_id, "x")


def test_get_order_not_found(shop):
    with pytest.raises(NotFoundError):
        shop.get_order("O9999")


def test_list_orders(shop):
    _prepare(shop)
    o1 = shop.create_order("张三")
    shop.create_order("李四")
    shop.cancel(o1, "x")

    assert [o["id"] for o in shop.list_orders()] == ["O0001", "O0002"]
    assert [o["id"] for o in shop.list_orders(status="cancelled")] == ["O0001"]
    assert [o["id"] for o in shop.list_orders(customer=" 李四 ")] == ["O0002"]

    with pytest.raises(ValidationError):
        shop.list_orders(status="bogus")


def test_order_numbers_not_reused(shop):
    _prepare(shop)
    o1 = shop.create_order("c")
    shop.cancel(o1, "x")
    assert shop.create_order("c") == "O0002"
