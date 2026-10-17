"""验收测试：S5 商品目录 add/get/update_price/set_active/list_products。"""

from datetime import datetime
from decimal import Decimal

import pytest

from shopkit import Shop
from shopkit.errors import NotFoundError, ValidationError


class FakeClock:
    """固定的本地时钟助手：返回固定 datetime，并记录被调用次数。"""

    def __init__(self, when=None):
        self.when = when if when is not None else datetime(2026, 3, 1, 9, 30, 0)
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.when


def make_shop():
    return Shop(clock=FakeClock())


# --- add_product -------------------------------------------------------------


def test_add_product_returns_expected_shape_with_string_price():
    shop = make_shop()
    result = shop.add_product("ABC-1", "Widget", "12", "Tools")
    assert result == {
        "sku": "ABC-1",
        "name": "Widget",
        "price": "12.00",
        "category": "tools",
        "active": True,
    }


def test_add_product_initializes_zero_stock():
    shop = make_shop()
    shop.add_product("ABC-1", "Widget", "12", "tools")
    assert shop.stock("ABC-1") == {"on_hand": 0, "reserved": 0, "available": 0}


def test_add_product_accepts_20_char_sku_and_rejects_21():
    shop = make_shop()
    ok = "A" * 20
    shop.add_product(ok, "n", "1", "c")
    with pytest.raises(ValidationError):
        shop.add_product("B" * 21, "n", "1", "c")


@pytest.mark.parametrize("sku", ["abc", "AB C", "AB.C", "", "-A_1", "AB/1"])
def test_add_product_rejects_invalid_sku(sku):
    shop = make_shop()
    with pytest.raises(ValidationError):
        shop.add_product(sku, "n", "1", "c")


def test_add_product_rejects_non_str_sku():
    shop = make_shop()
    with pytest.raises(ValidationError):
        shop.add_product(123, "n", "1", "c")


def test_add_product_rejects_duplicate_sku():
    shop = make_shop()
    shop.add_product("DUP", "first", "1", "c")
    with pytest.raises(ValidationError):
        shop.add_product("DUP", "second", "2", "c")


def test_add_product_strips_name_whitespace():
    shop = make_shop()
    result = shop.add_product("N1", "  Widget  ", "1", "c")
    assert result["name"] == "Widget"


@pytest.mark.parametrize("name", ["", "   ", None, 5])
def test_add_product_rejects_invalid_name(name):
    shop = make_shop()
    with pytest.raises(ValidationError):
        shop.add_product("N1", name, "1", "c")


@pytest.mark.parametrize("price", ["0", "-1", "abc", 1.5, True])
def test_add_product_rejects_invalid_price(price):
    shop = make_shop()
    with pytest.raises(ValidationError):
        shop.add_product("P1", "n", price, "c")


def test_add_product_normalizes_category():
    shop = make_shop()
    result = shop.add_product("C1", "n", "1", "  Tools  ")
    assert result["category"] == "tools"


@pytest.mark.parametrize("category", ["", "   ", None, 7])
def test_add_product_rejects_invalid_category(category):
    shop = make_shop()
    with pytest.raises(ValidationError):
        shop.add_product("C1", "n", "1", category)


@pytest.mark.parametrize("active", [1, 0, "true", None])
def test_add_product_rejects_non_bool_active(active):
    shop = make_shop()
    with pytest.raises(ValidationError):
        shop.add_product("A1", "n", "1", "c", active)


def test_add_product_active_can_be_false():
    shop = make_shop()
    result = shop.add_product("A1", "n", "1", "c", active=False)
    assert result["active"] is False


# --- get_product -------------------------------------------------------------


def test_get_product_returns_matching_product():
    shop = make_shop()
    shop.add_product("G1", "Gadget", "9.5", "Toys")
    assert shop.get_product("G1") == {
        "sku": "G1",
        "name": "Gadget",
        "price": "9.50",
        "category": "toys",
        "active": True,
    }


def test_get_product_missing_raises_not_found():
    shop = make_shop()
    with pytest.raises(NotFoundError):
        shop.get_product("NOPE")


# --- update_price ------------------------------------------------------------


def test_update_price_changes_and_returns_product():
    shop = make_shop()
    shop.add_product("U1", "n", "10", "c")
    result = shop.update_price("U1", "8.25")
    assert result["price"] == "8.25"
    assert shop.get_product("U1")["price"] == "8.25"


@pytest.mark.parametrize("price", ["0", "-5", "x", 1.5])
def test_update_price_rejects_invalid_price(price):
    shop = make_shop()
    shop.add_product("U2", "n", "10", "c")
    with pytest.raises(ValidationError):
        shop.update_price("U2", price)
    assert shop.get_product("U2")["price"] == "10.00"


def test_update_price_missing_sku_raises_not_found():
    shop = make_shop()
    with pytest.raises(NotFoundError):
        shop.update_price("NOPE", "5")


def test_update_price_validates_price_before_sku_lookup():
    # 检查顺序：参数 ValidationError 先于对象 NotFoundError
    shop = make_shop()
    with pytest.raises(ValidationError):
        shop.update_price("NOPE", "abc")


# --- set_active --------------------------------------------------------------


def test_set_active_toggles_and_returns_product():
    shop = make_shop()
    shop.add_product("S1", "n", "1", "c")
    assert shop.set_active("S1", False)["active"] is False
    assert shop.set_active("S1", True)["active"] is True


@pytest.mark.parametrize("active", [1, 0, "no", None])
def test_set_active_rejects_non_bool(active):
    shop = make_shop()
    shop.add_product("S2", "n", "1", "c")
    with pytest.raises(ValidationError):
        shop.set_active("S2", active)


def test_set_active_missing_sku_raises_not_found():
    shop = make_shop()
    with pytest.raises(NotFoundError):
        shop.set_active("NOPE", True)


# --- list_products -----------------------------------------------------------


def test_list_products_sorted_by_sku():
    shop = make_shop()
    for sku in ["BETA", "ALPHA", "MID"]:
        shop.add_product(sku, sku, "1", "c")
    skus = [p["sku"] for p in shop.list_products()]
    assert skus == ["ALPHA", "BETA", "MID"]


def test_list_products_filters_by_normalized_category():
    shop = make_shop()
    shop.add_product("A1", "a", "1", "Tools")
    shop.add_product("B1", "b", "1", "toys")
    result = shop.list_products(category="  TOOLS ")
    assert [p["sku"] for p in result] == ["A1"]


def test_list_products_active_only():
    shop = make_shop()
    shop.add_product("A1", "a", "1", "c", active=True)
    shop.add_product("B1", "b", "1", "c", active=False)
    result = shop.list_products(active_only=True)
    assert [p["sku"] for p in result] == ["A1"]


# --- 原子性 ------------------------------------------------------------------


def test_failed_add_product_leaves_no_state():
    shop = make_shop()
    with pytest.raises(ValidationError):
        shop.add_product("BAD", "n", "-1", "c")
    with pytest.raises(NotFoundError):
        shop.get_product("BAD")


def test_failed_duplicate_add_does_not_change_existing():
    shop = make_shop()
    shop.add_product("KEEP", "orig", "5", "c")
    with pytest.raises(ValidationError):
        shop.add_product("KEEP", "changed", "9", "other")
    assert shop.get_product("KEEP")["price"] == "5.00"
    assert shop.get_product("KEEP")["name"] == "orig"
