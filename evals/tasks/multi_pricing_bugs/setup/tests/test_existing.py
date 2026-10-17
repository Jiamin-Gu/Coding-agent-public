from decimal import Decimal

from pricing.checkout import checkout, subtotal


def test_subtotal():
    assert subtotal([{"sku": "apple", "qty": 2}, {"sku": "rice", "qty": 1}]) == Decimal("67.88")


def test_simple_checkout_hk():
    r = checkout([{"sku": "apple", "qty": 1}], "hk")
    assert r["subtotal"] == Decimal("3.99") and r["tax"] == Decimal("0.00")
    assert r["shipping"] == Decimal("8.00") and r["total"] == Decimal("11.99")
