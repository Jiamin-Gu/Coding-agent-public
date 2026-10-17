from datetime import datetime

import pytest

from shopkit import Shop
from shopkit.errors import (
    CouponError,
    NotFoundError,
    StockError,
    ValidationError,
)


def _food_shop(shop):
    shop.add_product("A-1", "Apple", "10.00", "food")
    shop.set_category_discount("food", 10)
    shop.set_tax_rate("food", 9)
    shop.add_coupon("SAVE10", "percent", 10)
    return shop


def test_quote_matches_spec_sample(shop):
    _food_shop(shop)
    q = shop.quote([{"sku": "A-1", "qty": 3}], "SAVE10")
    assert q == {
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


def test_quote_no_coupon(shop):
    _food_shop(shop)
    q = shop.quote([{"sku": "A-1", "qty": 3}])
    assert q["coupon"] is None
    assert q["coupon_discount"] == "0.00"
    assert q["lines"][0]["coupon_share"] == "0.00"
    assert q["tax"] == "2.43"  # round(27 * 9 / 100)
    assert q["total"] == "29.43"


def test_quote_merges_duplicate_skus(shop):
    _food_shop(shop)
    q = shop.quote([{"sku": "A-1", "qty": 1}, {"sku": "A-1", "qty": 2}])
    assert len(q["lines"]) == 1
    assert q["lines"][0]["qty"] == 3


def test_quote_tier_price(shop):
    shop.add_product("A-1", "Apple", "10.00", "food")
    shop.set_tier_price("A-1", 2, "9.00")
    shop.set_tier_price("A-1", 5, "8.00")
    assert shop.quote([{"sku": "A-1", "qty": 1}])["lines"][0]["unit_price"] == "10.00"
    assert shop.quote([{"sku": "A-1", "qty": 3}])["lines"][0]["unit_price"] == "9.00"
    assert shop.quote([{"sku": "A-1", "qty": 5}])["lines"][0]["unit_price"] == "8.00"
    assert shop.quote([{"sku": "A-1", "qty": 100}])["lines"][0]["unit_price"] == "8.00"


def test_tier_override_and_clear(shop):
    shop.add_product("A-1", "A", "10", "food")
    shop.set_tier_price("A-1", 2, "9")
    shop.set_tier_price("A-1", 2, "8")
    assert shop.quote([{"sku": "A-1", "qty": 2}])["lines"][0]["unit_price"] == "8.00"
    shop.clear_tier_prices("A-1")
    assert shop.quote([{"sku": "A-1", "qty": 2}])["lines"][0]["unit_price"] == "10.00"


@pytest.mark.parametrize("min_qty", [0, 1, True, 1.5, "2"])
def test_set_tier_price_bad_min_qty(shop, min_qty):
    shop.add_product("A-1", "A", "10", "food")
    with pytest.raises(ValidationError):
        shop.set_tier_price("A-1", min_qty, "5")


def test_set_tier_price_missing_sku(shop):
    with pytest.raises(NotFoundError):
        shop.set_tier_price("NOPE", 2, "5")


@pytest.mark.parametrize("percent", [-1, 91, True, 1.5, "5"])
def test_set_category_discount_bad(shop, percent):
    with pytest.raises(ValidationError):
        shop.set_category_discount("food", percent)


def test_set_category_discount_zero_cancels(shop):
    shop.add_product("A-1", "A", "10", "food")
    shop.set_category_discount("food", 50)
    shop.set_category_discount("food", 0)
    assert shop.quote([{"sku": "A-1", "qty": 1}])["lines"][0]["discount"] == "0.00"


@pytest.mark.parametrize("rate", ["31", "-1", "1.234", True, 1.5])
def test_set_tax_rate_bad(shop, rate):
    with pytest.raises(ValidationError):
        shop.set_tax_rate("food", rate)


def test_quote_coupon_share_rounding(shop):
    shop.add_product("A-1", "A", "10.00", "food")
    shop.add_product("B-2", "B", "20.00", "toys")
    shop.add_coupon("FIX10", "fixed", "10", min_subtotal="0")
    q = shop.quote(
        [{"sku": "A-1", "qty": 3}, {"sku": "B-2", "qty": 1}], "FIX10"
    )
    assert q["subtotal"] == "50.00"
    assert q["coupon_discount"] == "10.00"
    assert q["lines"][0]["coupon_share"] == "6.00"  # round(10*30/50)
    assert q["lines"][1]["coupon_share"] == "4.00"  # remainder
    assert q["total"] == "40.00"


def test_quote_validation_errors(shop):
    _food_shop(shop)
    with pytest.raises(ValidationError):
        shop.quote([])
    with pytest.raises(ValidationError):
        shop.quote([{"sku": "A-1", "qty": 0}])
    with pytest.raises(ValidationError):
        shop.quote([{"sku": "A-1", "qty": True}])
    with pytest.raises(ValidationError):
        shop.quote(["A-1"])
    with pytest.raises(NotFoundError):
        shop.quote([{"sku": "NOPE", "qty": 1}])


def test_quote_inactive_product(shop):
    _food_shop(shop)
    shop.set_active("A-1", False)
    with pytest.raises(ValidationError):
        shop.quote([{"sku": "A-1", "qty": 1}])


def test_coupon_lifecycle(shop):
    p = shop.add_coupon("  save10 ", "percent", 10, min_subtotal="5", expires="2026-12-31")
    assert p == {
        "code": "SAVE10",
        "kind": "percent",
        "value": 10,
        "min_subtotal": "5.00",
        "expires": "2026-12-31",
        "used_by": None,
    }
    assert shop.get_coupon("save10 ") == p
    with pytest.raises(NotFoundError):
        shop.get_coupon("NOPE")


@pytest.mark.parametrize("value", [0, 101, True, 1.5, "10"])
def test_add_percent_coupon_bad_value(shop, value):
    with pytest.raises(ValidationError):
        shop.add_coupon("C10", "percent", value)


@pytest.mark.parametrize("value", ["0", "-1"])
def test_add_fixed_coupon_bad_value(shop, value):
    with pytest.raises(ValidationError):
        shop.add_coupon("C10", "fixed", value)


def test_add_coupon_bad_code(shop):
    with pytest.raises(ValidationError):
        shop.add_coupon("ab", "fixed", "1")
    with pytest.raises(ValidationError):
        shop.add_coupon("bad code", "fixed", "1")


def test_add_coupon_duplicate(shop):
    shop.add_coupon("C10", "fixed", "1")
    with pytest.raises(ValidationError):
        shop.add_coupon("c1", "fixed", "2")


@pytest.mark.parametrize("expires", ["2026-1-01", "2026-13-01", "2026-02-30", "notadate"])
def test_add_coupon_bad_expires(shop, expires):
    with pytest.raises(ValidationError):
        shop.add_coupon("C10", "fixed", "1", expires=expires)


def test_coupon_min_subtotal(shop):
    shop.add_product("A-1", "A", "10", "food")
    shop.add_coupon("BIG", "fixed", "5", min_subtotal="100")
    with pytest.raises(CouponError):
        shop.quote([{"sku": "A-1", "qty": 1}], "BIG")


def test_coupon_unknown(shop):
    shop.add_product("A-1", "A", "10", "food")
    with pytest.raises(CouponError):
        shop.quote([{"sku": "A-1", "qty": 1}], "NOPE")


def test_coupon_expired(clock, shop):
    shop.add_product("A-1", "A", "10", "food")
    shop.add_coupon("EXP", "fixed", "1", expires="2026-03-01")
    # valid on the expiry day itself
    shop.quote([{"sku": "A-1", "qty": 1}], "EXP")
    clock.set(datetime(2026, 3, 2, 0, 0, 0))
    with pytest.raises(CouponError):
        shop.quote([{"sku": "A-1", "qty": 1}], "EXP")


def test_fixed_coupon_capped_at_subtotal(shop):
    shop.add_product("A-1", "A", "3.00", "food")
    shop.add_coupon("FIVE", "fixed", "5", min_subtotal="0")
    q = shop.quote([{"sku": "A-1", "qty": 1}], "FIVE")
    assert q["coupon_discount"] == "3.00"
    assert q["total"] == "0.00"
