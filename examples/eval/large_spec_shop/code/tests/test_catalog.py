import pytest

from shopkit import Shop
from shopkit.errors import NotFoundError, ValidationError


def test_add_product_view(shop):
    product = shop.add_product("A-1", "  Apple  ", "10", "  Food ")
    assert product == {
        "sku": "A-1",
        "name": "Apple",
        "price": "10.00",
        "category": "food",
        "active": True,
    }


@pytest.mark.parametrize("sku", ["a-1", "A_1", "", "A" * 21, "AB CD", "a b"])
def test_add_product_bad_sku(shop, sku):
    with pytest.raises(ValidationError):
        shop.add_product(sku, "X", "1", "cat")


def test_add_product_duplicate(shop):
    shop.add_product("A-1", "X", "1", "cat")
    with pytest.raises(ValidationError):
        shop.add_product("A-1", "Y", "2", "cat")


@pytest.mark.parametrize("price", ["0", "0.00", "-1"])
def test_add_product_price_must_be_positive(shop, price):
    with pytest.raises(ValidationError):
        shop.add_product("A-1", "X", price, "cat")


def test_add_product_bad_name_and_category(shop):
    with pytest.raises(ValidationError):
        shop.add_product("A-1", "   ", "1", "cat")
    with pytest.raises(ValidationError):
        shop.add_product("A-1", "X", "1", "   ")


def test_add_product_active_must_be_bool(shop):
    with pytest.raises(ValidationError):
        shop.add_product("A-1", "X", "1", "cat", active="yes")


def test_get_product_not_found(shop):
    with pytest.raises(NotFoundError):
        shop.get_product("NOPE")


def test_update_price(shop):
    shop.add_product("A-1", "X", "10", "cat")
    result = shop.update_price("A-1", "12.5")
    assert result["price"] == "12.50"
    assert shop.get_product("A-1")["price"] == "12.50"
    with pytest.raises(ValidationError):
        shop.update_price("A-1", "0")
    with pytest.raises(NotFoundError):
        shop.update_price("NOPE", "1")


def test_set_active(shop):
    shop.add_product("A-1", "X", "10", "cat")
    assert shop.set_active("A-1", False)["active"] is False
    with pytest.raises(ValidationError):
        shop.set_active("A-1", "no")
    with pytest.raises(NotFoundError):
        shop.set_active("NOPE", True)


def test_list_products(shop):
    shop.add_product("B-2", "B", "2", "Food")
    shop.add_product("A-1", "A", "1", "food")
    shop.add_product("C-3", "C", "3", "drink", active=False)

    all_products = shop.list_products()
    assert [p["sku"] for p in all_products] == ["A-1", "B-2", "C-3"]

    food = shop.list_products(category="  FOOD ")
    assert [p["sku"] for p in food] == ["A-1", "B-2"]

    active = shop.list_products(active_only=True)
    assert [p["sku"] for p in active] == ["A-1", "B-2"]


def test_list_products_validates_active_only(shop):
    with pytest.raises(ValidationError):
        shop.list_products(active_only="yes")
