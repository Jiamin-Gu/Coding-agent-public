import pytest

from shopkit.errors import NotFoundError, StockError, ValidationError


def test_new_product_stock_zero(shop):
    shop.add_product("A-1", "X", "1", "cat")
    assert shop.stock("A-1") == {"on_hand": 0, "reserved": 0, "available": 0}


def test_receive_and_log(shop, clock):
    shop.add_product("A-1", "X", "1", "cat")
    assert shop.receive("A-1", 5) == {"on_hand": 5, "reserved": 0, "available": 5}
    clock.set(clock.now.replace(hour=10))
    shop.receive("A-1", 3)
    assert shop.stock("A-1")["on_hand"] == 8
    assert shop.stock_log("A-1") == [
        {"at": "2026-03-01T09:30:00", "change": 5, "reason": "receive"},
        {"at": "2026-03-01T10:30:00", "change": 3, "reason": "receive"},
    ]


@pytest.mark.parametrize("qty", [True, False, 0, -1, 1.5, "3", None])
def test_receive_bad_qty(shop, qty):
    shop.add_product("A-1", "X", "1", "cat")
    with pytest.raises(ValidationError):
        shop.receive("A-1", qty)


def test_receive_not_found(shop):
    with pytest.raises(NotFoundError):
        shop.receive("NOPE", 1)


def test_adjust(shop):
    shop.add_product("A-1", "X", "1", "cat")
    shop.receive("A-1", 10)
    assert shop.adjust("A-1", -3, "  damaged ") == {
        "on_hand": 7,
        "reserved": 0,
        "available": 7,
    }
    log = shop.stock_log("A-1")
    assert log[-1]["change"] == -3
    assert log[-1]["reason"] == "damaged"


def test_adjust_validation(shop):
    shop.add_product("A-1", "X", "1", "cat")
    with pytest.raises(ValidationError):
        shop.adjust("A-1", 0, "x")
    with pytest.raises(ValidationError):
        shop.adjust("A-1", True, "x")
    with pytest.raises(ValidationError):
        shop.adjust("A-1", 1.0, "x")
    with pytest.raises(ValidationError):
        shop.adjust("A-1", 1, "   ")
    with pytest.raises(ValidationError):
        shop.adjust("A-1", 1, 5)


def test_adjust_below_reserved(shop):
    shop.add_product("A-1", "X", "1", "cat")
    shop.receive("A-1", 5)
    shop.set_reorder_level("A-1", 1)
    # place an order to reserve 5
    order_id = shop.create_order("c", [{"sku": "A-1", "qty": 5}])
    shop.place_order(order_id)

    with pytest.raises(StockError):
        shop.adjust("A-1", -1, "shrink")
    assert shop.stock("A-1")["on_hand"] == 5
    assert len(shop.stock_log("A-1")) == 1


def test_set_reorder_level(shop):
    shop.add_product("A-1", "X", "1", "cat")
    shop.set_reorder_level("A-1", 5)
    with pytest.raises(ValidationError):
        shop.set_reorder_level("A-1", -1)
    with pytest.raises(ValidationError):
        shop.set_reorder_level("A-1", True)
    with pytest.raises(NotFoundError):
        shop.set_reorder_level("NOPE", 1)


def test_low_stock(shop):
    shop.add_product("B-2", "B", "1", "cat")
    shop.add_product("A-1", "A", "1", "cat")
    shop.receive("A-1", 2)
    shop.receive("B-2", 10)
    shop.set_reorder_level("B-2", 3)  # 10 > 3 -> not low
    shop.set_reorder_level("A-1", 5)  # 2 <= 5 -> low
    assert shop.low_stock() == [
        {"sku": "A-1", "available": 2, "reorder_level": 5},
    ]


def test_low_stock_filters(shop):
    shop.add_product("A-1", "A", "1", "cat")
    shop.receive("A-1", 10)
    shop.set_reorder_level("A-1", 3)
    assert shop.low_stock() == []
    shop.set_reorder_level("A-1", 10)
    assert shop.low_stock() == [
        {"sku": "A-1", "available": 10, "reorder_level": 10}
    ]


def test_stock_log_not_found(shop):
    with pytest.raises(NotFoundError):
        shop.stock_log("NOPE")
    with pytest.raises(NotFoundError):
        shop.stock("NOPE")
