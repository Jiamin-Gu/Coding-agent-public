from datetime import datetime

import pytest

from shopkit import Shop
from shopkit.errors import CouponError, NotFoundError, ValidationError


def test_add_and_get_coupon_fixed(shop):
    coupon = shop.add_coupon(" save ", "fixed", "5", min_subtotal="20")
    assert coupon == {
        "code": "SAVE",
        "kind": "fixed",
        "value": "5.00",
        "min_subtotal": "20.00",
        "expires": None,
        "used_by": None,
    }
    assert shop.get_coupon("save") == coupon


def test_add_and_get_coupon_percent(shop):
    coupon = shop.add_coupon("TEN", "percent", 10)
    assert coupon["value"] == 10
    assert isinstance(coupon["value"], int)


@pytest.mark.parametrize("code", ["ab", "ABCDEFGHIJKLMNOPQ", "A B", "A-1", "", "  "])
def test_add_coupon_bad_code(shop, code):
    with pytest.raises(ValidationError):
        shop.add_coupon(code, "fixed", "5")


def test_add_coupon_duplicate(shop):
    shop.add_coupon("SAVE", "fixed", "5")
    with pytest.raises(ValidationError):
        shop.add_coupon("save", "fixed", "3")


def test_add_coupon_bad_kind(shop):
    with pytest.raises(ValidationError):
        shop.add_coupon("SAVE", "bogus", "5")


@pytest.mark.parametrize("value", ["0", "-1", 0, 101, True, "5"])
def test_add_coupon_bad_percent_value(shop, value):
    with pytest.raises(ValidationError):
        shop.add_coupon("SAVE", "percent", value)


def test_add_coupon_bad_fixed_value(shop):
    with pytest.raises(ValidationError):
        shop.add_coupon("SAVE", "fixed", "0")
    with pytest.raises(ValidationError):
        shop.add_coupon("SAVE", "fixed", "1.234")
    with pytest.raises(ValidationError):
        shop.add_coupon("SAVE", "fixed", 5.0)


@pytest.mark.parametrize("expires", ["2026-1-1", "notadate", "2026-13-01", "20260101"])
def test_add_coupon_bad_expires(shop, expires):
    with pytest.raises(ValidationError):
        shop.add_coupon("SAVE", "fixed", "5", expires=expires)


def test_get_coupon_not_found(shop):
    with pytest.raises(NotFoundError):
        shop.get_coupon("NOPE")


def test_coupon_expires_on_the_day_is_usable(shop, clock):
    shop.add_product("A-1", "A", "10", "food")
    shop.add_coupon("SAVE", "fixed", "2", expires="2026-03-01")
    # clock is 2026-03-01
    quote = shop.quote([{"sku": "A-1", "qty": 1}], coupon="save")
    assert quote["coupon_discount"] == "2.00"

    clock.set(datetime(2026, 3, 2, 9, 30, 0))
    with pytest.raises(CouponError):
        shop.quote([{"sku": "A-1", "qty": 1}], coupon="save")


def test_coupon_min_subtotal(shop):
    shop.add_product("A-1", "A", "10", "food")
    shop.add_coupon("SAVE", "fixed", "2", min_subtotal="50")
    with pytest.raises(CouponError):
        shop.quote([{"sku": "A-1", "qty": 4}], coupon="save")
    quote = shop.quote([{"sku": "A-1", "qty": 5}], coupon="save")
    assert quote["coupon_discount"] == "2.00"


def test_fixed_coupon_caps_at_subtotal(shop):
    shop.add_product("A-1", "A", "10", "food")
    shop.add_coupon("BIG", "fixed", "100")
    quote = shop.quote([{"sku": "A-1", "qty": 1}], coupon="big")
    assert quote["coupon_discount"] == "10.00"
    assert quote["total"] == "0.00"


def test_coupon_one_time_use_and_release(shop):
    shop.add_product("A-1", "A", "10", "food")
    shop.receive("A-1", 10)
    shop.add_coupon("SAVE", "fixed", "2")

    order_id = shop.create_order("c", [{"sku": "A-1", "qty": 1}], coupon="save")
    shop.place_order(order_id)
    assert shop.get_coupon("SAVE")["used_by"] == order_id

    with pytest.raises(CouponError):
        shop.quote([{"sku": "A-1", "qty": 1}], coupon="save")

    shop.cancel(order_id, "changed mind")
    assert shop.get_coupon("SAVE")["used_by"] is None

    shop2_order = shop.create_order("c", [{"sku": "A-1", "qty": 1}], coupon="save")
    shop.place_order(shop2_order)
    assert shop.get_coupon("SAVE")["used_by"] == shop2_order
