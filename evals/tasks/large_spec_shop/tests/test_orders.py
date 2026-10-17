import pytest

from shopkit import errors


def test_create_order(stocked):
    oid = stocked.create_order(" 张三 ", [{"sku": "APPLE", "qty": 2}, {"sku": "APPLE", "qty": 1}], coupon=" save10 ")
    assert oid == "O0001"
    assert stocked.get_order(oid) == {
        "id": "O0001", "customer": "张三", "status": "draft", "items": [{"sku": "APPLE", "qty": 3}],
        "coupon": "SAVE10", "pricing": None, "paid": None, "refund": None, "cancel_reason": None,
        "events": [{"at": "2026-03-01T09:00:00", "status": "draft"}]}
    assert stocked.create_order("李四") == "O0002"
    assert stocked.get_order("O0002")["items"] == []


def test_create_order_failures_do_not_consume_ids(stocked):
    with pytest.raises(errors.ValidationError):
        stocked.create_order("  ")
    with pytest.raises(errors.NotFoundError):
        stocked.create_order("张三", [{"sku": "NOPE", "qty": 1}])
    stocked.set_active("MILK", False)
    with pytest.raises(errors.ValidationError):
        stocked.create_order("张三", [{"sku": "MILK", "qty": 1}])
    with pytest.raises(errors.ValidationError):
        stocked.create_order("张三", [{"sku": "APPLE", "qty": 0}])
    assert stocked.list_orders() == []
    assert stocked.create_order("张三") == "O0001"


def test_add_and_remove_items(stocked):
    oid = stocked.create_order("张三", [{"sku": "MILK", "qty": 1}])
    assert stocked.add_item(oid, "APPLE", 2)["items"] == [{"sku": "MILK", "qty": 1}, {"sku": "APPLE", "qty": 2}]
    assert stocked.add_item(oid, "MILK", 3)["items"] == [{"sku": "MILK", "qty": 4}, {"sku": "APPLE", "qty": 2}]
    assert stocked.remove_item(oid, "MILK")["items"] == [{"sku": "APPLE", "qty": 2}]
    with pytest.raises(errors.NotFoundError):
        stocked.remove_item(oid, "MILK")
    with pytest.raises(errors.NotFoundError):
        stocked.add_item(oid, "NOPE", 1)
    with pytest.raises(errors.NotFoundError):
        stocked.add_item("O9999", "APPLE", 1)
    for qty in (0, True, "1"):
        with pytest.raises(errors.ValidationError):
            stocked.add_item(oid, "APPLE", qty)
    stocked.set_active("BOOK-1", False)
    with pytest.raises(errors.ValidationError):
        stocked.add_item(oid, "BOOK-1", 1)
    assert stocked.get_order(oid)["items"] == [{"sku": "APPLE", "qty": 2}]


def test_place_order_reserves_stock_and_snapshots_price(stocked, clock):
    stocked.add_coupon("TEN", "fixed", "10")
    oid = stocked.create_order("张三", [{"sku": "MILK", "qty": 3}], coupon="ten")
    clock.set("2026-03-01T10:00:00")
    o = stocked.place_order(oid)
    assert o["status"] == "placed" and o == stocked.get_order(oid)
    assert (o["pricing"]["subtotal"], o["pricing"]["coupon"], o["pricing"]["total"]) == ("36.00", "TEN", "26.00")
    assert [e["status"] for e in o["events"]] == ["draft", "placed"] and o["events"][1]["at"] == "2026-03-01T10:00:00"
    assert stocked.stock("MILK") == {"on_hand": 20, "reserved": 3, "available": 17}
    assert stocked.get_coupon("TEN")["used_by"] == oid
    stocked.update_price("MILK", "99")  # 已下单的订单保留下单时的价格
    assert stocked.get_order(oid)["pricing"]["total"] == "26.00"


def test_draft_uses_current_price_when_placed(stocked):
    oid = stocked.create_order("张三", [{"sku": "MILK", "qty": 1}])
    stocked.update_price("MILK", "15")
    assert stocked.place_order(oid)["pricing"]["total"] == "15.00"


def test_place_order_failures_change_nothing(stocked):
    stocked.add_coupon("ONCE", "fixed", "1")
    empty = stocked.create_order("张三")
    with pytest.raises(errors.ValidationError):
        stocked.place_order(empty)
    # 第二行库存不足：第一行也不能被预留
    short = stocked.create_order("张三", [{"sku": "APPLE", "qty": 5}, {"sku": "BOOK-1", "qty": 6}], coupon="ONCE")
    with pytest.raises(errors.StockError):
        stocked.place_order(short)
    assert stocked.stock("APPLE")["reserved"] == 0 and stocked.get_coupon("ONCE")["used_by"] is None
    assert stocked.get_order(short)["status"] == "draft" and stocked.get_order(short)["pricing"] is None
    # 优惠券已被别的订单占用
    first = stocked.create_order("李四", [{"sku": "APPLE", "qty": 1}], coupon="ONCE")
    stocked.place_order(first)
    second = stocked.create_order("王五", [{"sku": "APPLE", "qty": 2}], coupon="ONCE")
    with pytest.raises(errors.CouponError):
        stocked.place_order(second)
    assert stocked.stock("APPLE")["reserved"] == 1 and stocked.get_order(second)["status"] == "draft"
    # 加入后被下架的商品
    late = stocked.create_order("赵六", [{"sku": "MILK", "qty": 1}])
    stocked.set_active("MILK", False)
    with pytest.raises(errors.ValidationError):
        stocked.place_order(late)
    with pytest.raises(errors.NotFoundError):
        stocked.place_order("O9999")


def test_full_lifecycle(stocked, clock):
    oid = stocked.create_order("张三", [{"sku": "APPLE", "qty": 4}, {"sku": "BOOK-1", "qty": 1}])
    clock.set("2026-03-01T10:00:00")
    total = stocked.place_order(oid)["pricing"]["total"]
    assert total == "73.90"
    with pytest.raises(errors.ValidationError):
        stocked.pay(oid, "73.89")
    with pytest.raises(errors.ValidationError):
        stocked.pay(oid, 73.9)
    clock.set("2026-03-01T10:05:00")
    assert stocked.pay(oid, "73.9")["paid"] == "73.90"
    clock.set("2026-03-02T08:00:00")
    o = stocked.ship(oid)
    assert o["status"] == "shipped"
    assert stocked.stock("APPLE") == {"on_hand": 96, "reserved": 0, "available": 96}
    assert stocked.stock_log("BOOK-1")[-1] == {"at": "2026-03-02T08:00:00", "change": -1, "reason": "ship O0001"}
    clock.set("2026-03-03T18:00:00")
    o = stocked.deliver(oid)
    assert o["status"] == "delivered" and [(e["at"], e["status"]) for e in o["events"]] == [
        ("2026-03-01T09:00:00", "draft"), ("2026-03-01T10:00:00", "placed"), ("2026-03-01T10:05:00", "paid"),
        ("2026-03-02T08:00:00", "shipped"), ("2026-03-03T18:00:00", "delivered")]


def test_state_errors(stocked):
    oid = stocked.create_order("张三", [{"sku": "APPLE", "qty": 1}])
    for call in (lambda: stocked.pay(oid, "3.5"), lambda: stocked.ship(oid), lambda: stocked.deliver(oid)):
        with pytest.raises(errors.StateError):
            call()
    stocked.place_order(oid)
    for call in (lambda: stocked.place_order(oid), lambda: stocked.add_item(oid, "MILK", 1),
                 lambda: stocked.remove_item(oid, "APPLE"), lambda: stocked.set_coupon(oid, None),
                 lambda: stocked.ship(oid)):
        with pytest.raises(errors.StateError):
            call()
    stocked.pay(oid, "3.50")
    stocked.ship(oid)
    with pytest.raises(errors.StateError):
        stocked.cancel(oid, "不要了")
    stocked.deliver(oid)
    with pytest.raises(errors.StateError):
        stocked.cancel(oid, "不要了")
    assert stocked.get_order(oid)["status"] == "delivered"


def test_set_coupon(stocked):
    stocked.add_coupon("TEN", "fixed", "10")
    oid = stocked.create_order("张三", [{"sku": "MILK", "qty": 2}])
    assert stocked.set_coupon(oid, " ten")["coupon"] == "TEN"
    assert stocked.set_coupon(oid, None)["coupon"] is None
    assert stocked.place_order(oid)["pricing"]["coupon_discount"] == "0.00"


def test_cancel_draft_placed_paid(stocked):
    stocked.add_coupon("TEN", "fixed", "10")
    d = stocked.create_order("张三", [{"sku": "MILK", "qty": 2}])
    o = stocked.cancel(d, "  写错了 ")
    assert (o["status"], o["cancel_reason"], o["refund"]) == ("cancelled", "写错了", None)
    assert o["events"][-1]["status"] == "cancelled"

    p = stocked.create_order("李四", [{"sku": "MILK", "qty": 2}], coupon="TEN")
    stocked.place_order(p)
    stocked.cancel(p, "不想要了")
    assert stocked.stock("MILK") == {"on_hand": 20, "reserved": 0, "available": 20}
    assert stocked.get_coupon("TEN")["used_by"] is None
    reuse = stocked.create_order("王五", [{"sku": "MILK", "qty": 3}], coupon="TEN")  # 优惠券释放后可以再用
    assert stocked.place_order(reuse)["pricing"]["total"] == "26.00"

    paid = stocked.create_order("赵六", [{"sku": "BOOK-1", "qty": 2}])
    stocked.place_order(paid)
    stocked.pay(paid, "119.80")
    o = stocked.cancel(paid, "缺货")
    assert (o["status"], o["paid"], o["refund"]) == ("cancelled", "119.80", "119.80")
    assert stocked.stock("BOOK-1")["reserved"] == 0
    with pytest.raises(errors.ValidationError):
        stocked.cancel(reuse, "  ")
    with pytest.raises(errors.StateError):
        stocked.cancel(d, "再取消一次")


def test_list_orders(stocked):
    a = stocked.create_order("张三", [{"sku": "APPLE", "qty": 1}])
    b = stocked.create_order("李四", [{"sku": "APPLE", "qty": 1}])
    c = stocked.create_order("张三")
    stocked.place_order(b)
    stocked.cancel(c, "x")
    assert [o["id"] for o in stocked.list_orders()] == [a, b, c]
    assert [o["id"] for o in stocked.list_orders(status="placed")] == [b]
    assert [o["id"] for o in stocked.list_orders(customer=" 张三 ")] == [a, c]
    assert [o["id"] for o in stocked.list_orders(status="cancelled", customer="张三")] == [c]
    assert stocked.list_orders(status="placed")[0] == stocked.get_order(b)
    with pytest.raises(errors.ValidationError):
        stocked.list_orders(status="lost")
