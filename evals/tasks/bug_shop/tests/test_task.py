import pytest

from shop.cart import Cart


def make_cart(*items):
    cart = Cart()
    for name, price, qty in items:
        cart.add(name, price, qty)
    return cart


def test_subtotal_uses_quantity():
    assert make_cart(("杯子", 30, 3)).subtotal() == 90


def test_percent_coupon():
    assert make_cart(("杯子", 30, 3)).total("SAVE10") == 81


def test_threshold_coupon_inclusive():
    assert make_cart(("书", 50, 2)).total("FULL100") == 80
    assert make_cart(("书", 99, 1)).total("FULL100") == 99


def test_no_coupon():
    assert make_cart(("书", 10.5, 2)).total() == 21


def test_unknown_coupon():
    with pytest.raises(ValueError):
        make_cart(("书", 10, 1)).total("NOPE")
