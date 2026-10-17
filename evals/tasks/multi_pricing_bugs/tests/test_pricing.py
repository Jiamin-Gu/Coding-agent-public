from decimal import Decimal as D

from pricing.checkout import checkout
from pricing.promotions import buy_one_get_one
from pricing.shipping import shipping_fee
from pricing.tax import tax_for


def test_bogo_odd_and_even():
    assert buy_one_get_one([{"sku": "banana", "qty": 3}], "banana") == D("1.25")
    assert buy_one_get_one([{"sku": "banana", "qty": 4}], "banana") == D("2.50")
    assert buy_one_get_one([{"sku": "banana", "qty": 1}], "banana") == D("0")


def test_tax_rounds_half_up():
    assert D(str(tax_for(D("12.25"), "cn"))) == D("0.74")   # 0.735 → 0.74
    assert D(str(tax_for(D("0.25"), "us"))) == D("0.02")    # 0.02 正好


def test_tax_on_discounted_amount():
    r = checkout([{"sku": "milk", "qty": 2}], "cn")          # 24.50 打九折 → 22.05
    assert r["merchandise"] == D("22.05")
    assert r["tax"] == D("1.32")                              # 22.05 × 6% = 1.323


def test_free_shipping_uses_discounted_amount():
    # 原价 102.25（满 99），乳品九折后 92.025 → 92.03，不满 99：要收运费
    r = checkout([{"sku": "cheese", "qty": 2}, {"sku": "milk", "qty": 1}], "hk")
    assert r["subtotal"] == D("102.25") and r["merchandise"] == D("92.03")
    assert r["shipping"] == D("8.00")                         # 2kg，没有超重
    # 打折后仍然满 99：免运费
    r2 = checkout([{"sku": "rice", "qty": 2}], "hk")
    assert r2["shipping"] == D("0.00")


def test_weight_surcharge_rounds_up():
    assert shipping_fee([{"sku": "milk", "qty": 4}], D("10")) == D("10")    # 4kg：超 1kg → 8+2
    assert shipping_fee([{"sku": "milk", "qty": 3}, {"sku": "apple", "qty": 1}], D("10")) == D("10")  # 3.2kg → 超 0.2 按 1kg
    assert shipping_fee([{"sku": "milk", "qty": 3}], D("10")) == D("8")     # 正好 3kg


def test_full_checkout():
    lines = [{"sku": "banana", "qty": 3}, {"sku": "milk", "qty": 1}, {"sku": "apple", "qty": 2}]
    r = checkout(lines, "us")
    # 原价 3.75+12.25+7.98=23.98；优惠 1.25+1.225=2.475；打折后 21.505 → 21.51
    assert r["subtotal"] == D("23.98")
    assert r["discount"] == D("2.48")
    assert r["merchandise"] == D("21.51")
    assert r["tax"] == D("1.72")                 # 21.505 × 8% = 1.7204
    assert r["shipping"] == D("8.00")            # 1.85kg
    assert r["total"] == D("31.23")              # 21.505 + 1.72 + 8 = 31.225 → 31.23
