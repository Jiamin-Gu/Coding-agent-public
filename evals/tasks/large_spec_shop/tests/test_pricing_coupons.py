import pytest

from shopkit import errors


def line(sku, category, qty, unit, total, discount, net, share, tax):
    return {"sku": sku, "category": category, "qty": qty, "unit_price": unit, "line_total": total,
            "discount": discount, "net": net, "coupon_share": share, "tax": tax}


def test_quote_basic(stocked):
    assert stocked.quote([{"sku": "APPLE", "qty": 4}]) == {
        "lines": [line("APPLE", "food", 4, "3.50", "14.00", "0.00", "14.00", "0.00", "0.00")],
        "subtotal": "14.00", "coupon": None, "coupon_discount": "0.00", "tax": "0.00", "total": "14.00"}


def test_quote_merges_duplicate_skus_in_first_seen_order(stocked):
    q = stocked.quote([{"sku": "MILK", "qty": 1}, {"sku": "APPLE", "qty": 2}, {"sku": "MILK", "qty": 3}])
    assert [(ln["sku"], ln["qty"]) for ln in q["lines"]] == [("MILK", 4), ("APPLE", 2)]
    assert q["subtotal"] == "55.00"


def test_tier_prices(stocked):
    stocked.set_tier_price("APPLE", 10, "3.00")
    stocked.set_tier_price("APPLE", 50, "2.50")

    def unit(qty):
        return stocked.quote([{"sku": "APPLE", "qty": qty}])["lines"][0]["unit_price"]
    assert [unit(q) for q in (9, 10, 49, 50, 60)] == ["3.50", "3.00", "3.00", "2.50", "2.50"]
    assert stocked.quote([{"sku": "APPLE", "qty": 60}])["lines"][0]["line_total"] == "150.00"
    stocked.set_tier_price("APPLE", 10, "3.20")  # 覆盖
    assert unit(10) == "3.20"
    stocked.clear_tier_prices("APPLE")
    assert unit(60) == "3.50"


def test_tier_price_validation(stocked):
    for args in (("APPLE", 1, "3"), ("APPLE", True, "3"), ("APPLE", "10", "3"), ("APPLE", 10, "0"), ("APPLE", 10, 2.5)):
        with pytest.raises(errors.ValidationError):
            stocked.set_tier_price(*args)
    with pytest.raises(errors.NotFoundError):
        stocked.set_tier_price("NOPE", 10, "3")
    with pytest.raises(errors.NotFoundError):
        stocked.clear_tier_prices("NOPE")


def test_category_discount_and_tax(stocked):
    stocked.set_category_discount(" FOOD", 10)
    stocked.set_tax_rate("food", "9")
    q = stocked.quote([{"sku": "MILK", "qty": 2}])
    # 24.00 打九折 → 21.60；税 21.60 × 9% = 1.944 → 1.94
    assert q["lines"][0] == line("MILK", "food", 2, "12.00", "24.00", "2.40", "21.60", "0.00", "1.94")
    assert (q["subtotal"], q["tax"], q["total"]) == ("21.60", "1.94", "23.54")
    stocked.set_category_discount("food", 0)  # 取消折扣
    assert stocked.quote([{"sku": "MILK", "qty": 2}])["lines"][0]["discount"] == "0.00"


def test_rule_validation(stocked):
    for pct in (91, -1, True, "10", 10.0):
        with pytest.raises(errors.ValidationError):
            stocked.set_category_discount("food", pct)
    for rate in ("30.01", "-1", "12.345", 9.5, True):
        with pytest.raises(errors.ValidationError):
            stocked.set_tax_rate("food", rate)
    with pytest.raises(errors.ValidationError):
        stocked.set_category_discount("  ", 10)
    stocked.set_tax_rate("food", "30")
    stocked.set_category_discount("toys", 20)  # 还没有商品的类别也可以设置


def test_full_pricing_with_coupon_allocation(stocked):
    stocked.set_category_discount("food", 10)
    stocked.set_tax_rate("food", "9")
    stocked.set_tax_rate("book", "13")
    stocked.add_coupon(" save10 ", "percent", 10)
    q = stocked.quote([{"sku": "APPLE", "qty": 3}, {"sku": "MILK", "qty": 2}, {"sku": "BOOK-1", "qty": 1}], coupon="save10")
    # 小计 9.45 + 21.60 + 59.90 = 90.95；优惠 90.95 × 10% = 9.095 → 9.10
    # 分摊：9.10×9.45/90.95=0.9455→0.95，9.10×21.60/90.95=2.1612→2.16，最后一行 9.10-0.95-2.16=5.99
    # 税：8.50×9%=0.765→0.77，19.44×9%=1.7496→1.75，53.91×13%=7.0083→7.01
    assert q["lines"] == [
        line("APPLE", "food", 3, "3.50", "10.50", "1.05", "9.45", "0.95", "0.77"),
        line("MILK", "food", 2, "12.00", "24.00", "2.40", "21.60", "2.16", "1.75"),
        line("BOOK-1", "book", 1, "59.90", "59.90", "0.00", "59.90", "5.99", "7.01"),
    ]
    assert (q["subtotal"], q["coupon"], q["coupon_discount"], q["tax"], q["total"]) == (
        "90.95", "SAVE10", "9.10", "9.53", "91.38")


def test_fixed_coupon_remainder_goes_to_last_line(stocked):
    stocked.add_coupon("TEN", "fixed", "10")
    q = stocked.quote([{"sku": "APPLE", "qty": 1}, {"sku": "MILK", "qty": 1}, {"sku": "BOOK-1", "qty": 1}], coupon="TEN")
    # 小计 75.40；10×3.50/75.40=0.464→0.46，10×12/75.40=1.592→1.59，最后一行 7.95
    assert [ln["coupon_share"] for ln in q["lines"]] == ["0.46", "1.59", "7.95"]
    assert (q["subtotal"], q["coupon_discount"], q["total"]) == ("75.40", "10.00", "65.40")


def test_fixed_coupon_capped_at_subtotal(stocked):
    stocked.set_tax_rate("food", "9")
    stocked.add_coupon("BIG100", "fixed", "100")
    q = stocked.quote([{"sku": "APPLE", "qty": 2}], coupon="BIG100")
    assert (q["coupon_discount"], q["lines"][0]["coupon_share"], q["tax"], q["total"]) == ("7.00", "7.00", "0.00", "0.00")


def test_coupon_min_subtotal(stocked):
    stocked.add_coupon("MIN50", "fixed", "5", min_subtotal="50")
    with pytest.raises(errors.CouponError):
        stocked.quote([{"sku": "APPLE", "qty": 10}], coupon="MIN50")  # 35.00 < 50
    assert stocked.quote([{"sku": "APPLE", "qty": 20}], coupon="MIN50")["total"] == "65.00"


def test_coupon_expiry_is_inclusive(stocked, clock):
    stocked.add_coupon("SPRING", "percent", 20, expires="2026-03-31")
    clock.set("2026-03-31T23:59:59")
    assert stocked.quote([{"sku": "MILK", "qty": 1}], coupon="spring")["coupon_discount"] == "2.40"
    clock.set("2026-04-01T00:00:00")
    with pytest.raises(errors.CouponError):
        stocked.quote([{"sku": "MILK", "qty": 1}], coupon="SPRING")


def test_unknown_coupon_and_no_side_effects(stocked):
    with pytest.raises(errors.CouponError):
        stocked.quote([{"sku": "MILK", "qty": 1}], coupon="NOPE")
    stocked.add_coupon("ONCE", "fixed", "1")
    stocked.quote([{"sku": "MILK", "qty": 1}], coupon="ONCE")
    stocked.quote([{"sku": "MILK", "qty": 1}], coupon="ONCE")  # 报价不占用优惠券
    assert stocked.get_coupon("ONCE")["used_by"] is None
    assert stocked.stock("MILK") == {"on_hand": 20, "reserved": 0, "available": 20}  # 报价不检查、不预留库存
    assert stocked.quote([{"sku": "MILK", "qty": 999}])["subtotal"] == "11988.00"


@pytest.mark.parametrize("items", [
    [], [{"sku": "APPLE", "qty": 0}], [{"sku": "APPLE", "qty": True}], [{"sku": "APPLE", "qty": "2"}],
    [{"sku": "APPLE"}], ["APPLE"], "APPLE",
])
def test_quote_invalid_items(stocked, items):
    with pytest.raises(errors.ValidationError):
        stocked.quote(items)


def test_quote_unknown_and_inactive(stocked):
    with pytest.raises(errors.NotFoundError):
        stocked.quote([{"sku": "NOPE", "qty": 1}])
    stocked.set_active("MILK", False)
    with pytest.raises(errors.ValidationError):
        stocked.quote([{"sku": "MILK", "qty": 1}])


def test_add_and_get_coupon(stocked):
    assert stocked.add_coupon(" save10 ", "percent", 10) == {
        "code": "SAVE10", "kind": "percent", "value": 10, "min_subtotal": "0.00", "expires": None, "used_by": None}
    assert stocked.add_coupon("min50", "fixed", "5", min_subtotal="50", expires="2026-12-31") == {
        "code": "MIN50", "kind": "fixed", "value": "5.00", "min_subtotal": "50.00", "expires": "2026-12-31",
        "used_by": None}
    assert stocked.get_coupon(" Save10")["code"] == "SAVE10"
    with pytest.raises(errors.NotFoundError):
        stocked.get_coupon("NOPE")


@pytest.mark.parametrize("args,kwargs", [
    (("ab", "fixed", "5"), {}), (("A-B-C", "fixed", "5"), {}), (("A" * 17, "fixed", "5"), {}),
    (("CODE", "bogus", "5"), {}), (("CODE", "fixed", "0"), {}), (("CODE", "fixed", 5.5), {}),
    (("CODE", "percent", 0), {}), (("CODE", "percent", 101), {}), (("CODE", "percent", True), {}),
    (("CODE", "percent", "10"), {}), (("CODE", "fixed", "5"), {"min_subtotal": "-1"}),
    (("CODE", "fixed", "5"), {"expires": "2026-2-1"}), (("CODE", "fixed", "5"), {"expires": "2026-02-30"}),
])
def test_add_coupon_invalid(stocked, args, kwargs):
    with pytest.raises(errors.ValidationError):
        stocked.add_coupon(*args, **kwargs)
    with pytest.raises(errors.NotFoundError):
        stocked.get_coupon("CODE")


def test_coupon_code_is_unique_case_insensitive(stocked):
    stocked.add_coupon("SAVE10", "percent", 10)
    with pytest.raises(errors.ValidationError):
        stocked.add_coupon("save10", "fixed", "1")
    assert stocked.get_coupon("SAVE10")["kind"] == "percent"
