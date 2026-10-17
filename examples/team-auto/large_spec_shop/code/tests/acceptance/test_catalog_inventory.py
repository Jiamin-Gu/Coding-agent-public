import pytest

from shopkit import Shop
from shopkit.errors import NotFoundError, StateError, StockError, ValidationError


def test_add_and_get_product(shop):
    p = shop.add_product("A-1", "  Apple  ", "10.00", " Food ")
    assert p == {
        "sku": "A-1",
        "name": "Apple",
        "price": "10.00",
        "category": "food",
        "active": True,
    }
    assert shop.get_product("A-1") == p


def test_add_product_duplicate(shop):
    shop.add_product("A-1", "Apple", "10", "food")
    with pytest.raises(ValidationError):
        shop.add_product("A-1", "Other", "5", "food")


@pytest.mark.parametrize(
    "sku",
    ["a-1", "ABCDEFGHIJKLMNOPQRSTUVW", "", "A 1", "A_1", "A.B"],
)
def test_add_product_bad_sku(shop, sku):
    with pytest.raises(ValidationError):
        shop.add_product(sku, "Apple", "10", "food")


@pytest.mark.parametrize("price", ["", " "])
def test_add_product_blank_name(shop, price):
    with pytest.raises(ValidationError):
        shop.add_product("A-1", price, "10", "food")


@pytest.mark.parametrize("price", ["0", "0.00", "-1"])
def test_add_product_bad_price(shop, price):
    with pytest.raises(ValidationError):
        shop.add_product("A-1", "Apple", price, "food")


def test_add_product_bad_active(shop):
    with pytest.raises(ValidationError):
        shop.add_product("A-1", "Apple", "10", "food", active="yes")


def test_add_product_bad_category(shop):
    with pytest.raises(ValidationError):
        shop.add_product("A-1", "Apple", "10", "   ")


def test_get_product_missing(shop):
    with pytest.raises(NotFoundError):
        shop.get_product("NOPE")


def test_update_price_and_set_active(shop):
    shop.add_product("A-1", "Apple", "10", "food")
    assert shop.update_price("A-1", "12.5")["price"] == "12.50"
    assert shop.set_active("A-1", False)["active"] is False
    with pytest.raises(NotFoundError):
        shop.update_price("NOPE", "1")
    with pytest.raises(ValidationError):
        shop.set_active("A-1", 1)


def test_list_products(shop):
    shop.add_product("B-2", "B", "1", "Food")
    shop.add_product("A-1", "A", "1", "toys")
    shop.add_product("C-3", "C", "1", "food", active=False)
    assert [p["sku"] for p in shop.list_products()] == ["A-1", "B-2", "C-3"]
    assert [p["sku"] for p in shop.list_products(category=" FOOD ")] == ["B-2", "C-3"]
    assert [p["sku"] for p in shop.list_products(active_only=True)] == ["A-1", "B-2"]


def test_receive_and_stock(shop):
    shop.add_product("A-1", "A", "1", "food")
    assert shop.receive("A-1", 5) == {"on_hand": 5, "reserved": 0, "available": 5}
    assert shop.stock("A-1") == {"on_hand": 5, "reserved": 0, "available": 5}


@pytest.mark.parametrize("qty", [0, -1, True, 1.5, "1"])
def test_receive_bad_qty(shop, qty):
    shop.add_product("A-1", "A", "1", "food")
    with pytest.raises(ValidationError):
        shop.receive("A-1", qty)


def test_receive_missing(shop):
    with pytest.raises(NotFoundError):
        shop.receive("NOPE", 1)


def test_adjust(shop, clock):
    shop.add_product("A-1", "A", "1", "food")
    shop.receive("A-1", 10)
    shop.adjust("A-1", -3, "  shrink  ")
    assert shop.stock("A-1")["on_hand"] == 7
    log = shop.stock_log("A-1")
    assert log == [
        {"at": "2026-03-01T09:30:00", "change": 10, "reason": "receive"},
        {"at": "2026-03-01T09:30:00", "change": -3, "reason": "shrink"},
    ]


@pytest.mark.parametrize("delta", [0, True, 1.5, "1"])
def test_adjust_bad_delta(shop, delta):
    shop.add_product("A-1", "A", "1", "food")
    with pytest.raises(ValidationError):
        shop.adjust("A-1", delta, "x")


def test_adjust_bad_reason(shop):
    shop.add_product("A-1", "A", "1", "food")
    with pytest.raises(ValidationError):
        shop.adjust("A-1", 1, "   ")


def test_adjust_below_reserved_is_atomic(shop, clock):
    shop.add_product("A-1", "A", "10", "food")
    shop.receive("A-1", 10)
    shop.create_order("c", [{"sku": "A-1", "qty": 8}])
    shop.place_order("O0001")
    assert shop.stock("A-1") == {"on_hand": 10, "reserved": 8, "available": 2}
    with pytest.raises(StockError):
        shop.adjust("A-1", -3, "count")
    # atomic: nothing changed
    assert shop.stock("A-1") == {"on_hand": 10, "reserved": 8, "available": 2}
    assert len(shop.stock_log("A-1")) == 1


def test_reorder_level_and_low_stock(shop):
    shop.add_product("A-1", "A", "1", "food")
    shop.add_product("B-2", "B", "1", "food")
    shop.receive("A-1", 5)
    shop.set_reorder_level("A-1", 5)
    shop.set_reorder_level("B-2", 1)
    # SPEC: reorder_level > 0 and available <= reorder_level (0 <= 1 counts).
    assert [x["sku"] for x in shop.low_stock()] == ["A-1", "B-2"]
    assert shop.low_stock() == [
        {"sku": "A-1", "available": 5, "reorder_level": 5},
        {"sku": "B-2", "available": 0, "reorder_level": 1},
    ]


@pytest.mark.parametrize("level", [-1, True, 1.5, "1"])
def test_set_reorder_level_bad(shop, level):
    shop.add_product("A-1", "A", "1", "food")
    with pytest.raises(ValidationError):
        shop.set_reorder_level("A-1", level)


def test_stock_log_missing(shop):
    with pytest.raises(NotFoundError):
        shop.stock_log("NOPE")
