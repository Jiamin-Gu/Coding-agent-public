from decimal import Decimal

import pytest

from shopkit.errors import (
    CouponError,
    NotFoundError,
    ValidationError,
)


def test_tier_price_selection(shop):
    shop.add_product("A-1", "A", "10", "food")
    shop.set_tier_price("A-1", 5, "8")
    shop.set_tier_price("A-1", 10, "6")

    assert shop.quote([{"sku": "A-1", "qty": 3}])["lines"][0]["unit_price"] == "10.00"
    assert shop.quote([{"sku": "A-1", "qty": 5}])["lines"][0]["unit_price"] == "8.00"
    assert shop.quote([{"sku": "A-1", "qty": 7}])["lines"][0]["unit_price"] == "8.00"
    assert shop.quote([{"sku": "A-1", "qty": 12}])["lines"][0]["unit_price"] == "6.00"


def test_tier_price_overwrite_and_clear(shop):
    shop.add_product("A-1", "A", "10", "food")
    shop.set_tier_price("A-1", 5, "8")
    shop.set_tier_price("A-1", 5, "7")
    assert shop.quote([{"sku": "A-1", "qty": 5}])["lines"][0]["unit_price"] == "7.00"
    shop.clear_tier_prices("A-1")
    assert shop.quote([{"sku": "A-1", "qty": 5}])["lines"][0]["unit_price"] == "10.00"


def test_tier_price_validation(shop):
    shop.add_product("A-1", "A", "10", "food")
    with pytest.raises(ValidationError):
        shop.set_tier_price("A-1", 1, "5")
    with pytest.raises(ValidationError):
        shop.set_tier_price("A-1", True, "5")
    with pytest.raises(ValidationError):
        shop.set_tier_price("A-1", 5, "0")
    with pytest.raises(NotFoundError):
        shop.set_tier_price("NOPE", 5, "5")


def test_quote_worked_example(shop):
    shop.add_product("A-1", "A", "10", "food")
    shop.add_coupon("SAVE10", "percent", 10)
    shop.set_category_discount("food", 10)
    shop.set_tax_rate("food", "9")

    quote = shop.quote([{"sku": "A-1", "qty": 3}], coupon="save10")
    assert quote == {
        "lines": [
            {
                "sku": "A-1",
                "category": "food",
                "qty": 3,
                "unit_price": "10.00",
                "line_total": "30.00",
                "discount": "3.00",
                "net": "27.00",
                "coupon_share": "2.70",
                "tax": "2.19",
            }
        ],
        "subtotal": "27.00",
        "coupon": "SAVE10",
        "coupon_discount": "2.70",
        "tax": "2.19",
        "total": "26.49",
    }


def test_quote_merges_duplicate_skus(shop):
    shop.add_product("A-1", "A", "10", "food")
    shop.add_product("B-2", "B", "5", "food")
    quote = shop.quote(
        [{"sku": "B-2", "qty": 1}, {"sku": "A-1", "qty": 2}, {"sku": "B-2", "qty": 3}]
    )
    assert [line["sku"] for line in quote["lines"]] == ["B-2", "A-1"]
    assert quote["lines"][0]["qty"] == 4
    assert quote["lines"][1]["qty"] == 2


def test_quote_coupon_allocation_sums_to_discount(shop):
    shop.add_product("A-1", "A", "10", "food")
    shop.add_product("B-2", "B", "7", "drink")
    shop.add_coupon("CUT", "fixed", "5")
    quote = shop.quote(
        [{"sku": "A-1", "qty": 3}, {"sku": "B-2", "qty": 2}], coupon="cut"
    )
    shares = [Decimal(line["coupon_share"]) for line in quote["lines"]]
    assert sum(shares) == Decimal(quote["coupon_discount"])
    assert quote["coupon_discount"] == "5.00"


def test_quote_is_side_effect_free(shop):
    shop.add_product("A-1", "A", "10", "food")
    shop.add_coupon("SAVE", "fixed", "2")
    shop.quote([{"sku": "A-1", "qty": 3}], coupon="save")
    assert shop.get_coupon("SAVE")["used_by"] is None
    assert shop.stock("A-1")["reserved"] == 0


@pytest.mark.parametrize(
    "items",
    [
        [],
        "A-1",
        [{"sku": "A-1"}],
        [{"sku": "A-1", "qty": 0}],
        [{"sku": "A-1", "qty": -1}],
        [{"sku": "A-1", "qty": True}],
        [{"sku": "A-1", "qty": 1.5}],
        [{"qty": 1}],
        [{"sku": 5, "qty": 1}],
        ["A-1"],
    ],
)
def test_quote_invalid_items(shop, items):
    shop.add_product("A-1", "A", "10", "food")
    with pytest.raises(ValidationError):
        shop.quote(items)


def test_quote_unknown_sku(shop):
    with pytest.raises(NotFoundError):
        shop.quote([{"sku": "NOPE", "qty": 1}])


def test_quote_inactive_product(shop):
    shop.add_product("A-1", "A", "10", "food", active=False)
    with pytest.raises(ValidationError):
        shop.quote([{"sku": "A-1", "qty": 1}])


def test_quote_unknown_coupon(shop):
    shop.add_product("A-1", "A", "10", "food")
    with pytest.raises(CouponError):
        shop.quote([{"sku": "A-1", "qty": 1}], coupon="NOPE")
    with pytest.raises(ValidationError):
        shop.quote([{"sku": "A-1", "qty": 1}], coupon=123)


def test_category_discount_and_tax(shop):
    shop.add_product("A-1", "A", "100", "food")
    shop.set_category_discount("food", 20)
    shop.set_tax_rate("food", "13")
    quote = shop.quote([{"sku": "A-1", "qty": 1}])
    line = quote["lines"][0]
    assert line["line_total"] == "100.00"
    assert line["discount"] == "20.00"
    assert line["net"] == "80.00"
    assert line["tax"] == "10.40"
    assert quote["total"] == "90.40"


def test_tax_rate_validation(shop):
    with pytest.raises(ValidationError):
        shop.set_tax_rate("food", "31")
    with pytest.raises(ValidationError):
        shop.set_tax_rate("food", "-1")
    with pytest.raises(ValidationError):
        shop.set_tax_rate("food", "1.234")


def test_category_discount_validation(shop):
    with pytest.raises(ValidationError):
        shop.set_category_discount("food", 91)
    with pytest.raises(ValidationError):
        shop.set_category_discount("food", -1)
    with pytest.raises(ValidationError):
        shop.set_category_discount("food", True)
    # zero cancels
    shop.set_category_discount("food", 10)
    shop.set_category_discount("food", 0)
