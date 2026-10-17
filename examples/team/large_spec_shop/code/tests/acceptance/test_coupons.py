"""优惠券验收测试（S11）：add_coupon/get_coupon 的校验、规范化、返回格式与占用/过期状态。"""

from datetime import datetime
from decimal import Decimal

import pytest

from shopkit import CouponError, NotFoundError, Shop, ValidationError
from shopkit.money import format_money


class FixedClock:
    """可固定的 clock，便于测试过期判断。"""

    def __init__(self, moment):
        self.moment = moment

    def __call__(self):
        return self.moment


@pytest.fixture
def shop():
    return Shop(clock=FixedClock(datetime(2026, 1, 15, 12, 0, 0)))


# ---------------------------------------------------------------------------
# add_coupon：返回格式
# ---------------------------------------------------------------------------

def test_add_fixed_coupon_returns_formatted_dict(shop):
    result = shop.add_coupon("SAVE5", "fixed", "5")
    assert result == {
        "code": "SAVE5",
        "kind": "fixed",
        "value": "5.00",
        "min_subtotal": "0.00",
        "expires": None,
        "used_by": None,
    }


def test_add_percent_coupon_value_stays_int(shop):
    result = shop.add_coupon("SAVE15", "percent", 15)
    assert result["kind"] == "percent"
    assert result["value"] == 15
    # 契约：percent 的 value 保持 int，且不能是 bool
    assert isinstance(result["value"], int)
    assert not isinstance(result["value"], bool)


def test_add_coupon_normalizes_code(shop):
    result = shop.add_coupon("  save5  ", "fixed", "1")
    assert result["code"] == "SAVE5"
    # 所有接收优惠券代码的参数都按同样方式规范化
    assert shop.get_coupon(" save5 ")["code"] == "SAVE5"


# ---------------------------------------------------------------------------
# add_coupon：参数校验
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "code",
    ["", "AB", "A" * 17, "AB C", "AB-1", "A_B", 123, None, ["SAVE5"]],
)
def test_add_coupon_rejects_bad_code(shop, code):
    with pytest.raises(ValidationError):
        shop.add_coupon(code, "fixed", "1")


def test_add_coupon_rejects_duplicate_after_normalization(shop):
    shop.add_coupon("SAVE5", "fixed", "1")
    with pytest.raises(ValidationError):
        shop.add_coupon(" save5 ", "fixed", "2")


@pytest.mark.parametrize("kind", ["bogus", "", 5, None])
def test_add_coupon_rejects_invalid_kind(shop, kind):
    with pytest.raises(ValidationError):
        shop.add_coupon("SAVE5", kind, "1")


@pytest.mark.parametrize("value", ["0", "-1", "1.234", 0, -5, 1.5, None, True])
def test_add_fixed_coupon_rejects_bad_value(shop, value):
    with pytest.raises(ValidationError):
        shop.add_coupon("SAVE5", "fixed", value)


@pytest.mark.parametrize("value", [0, 101, -1, True, "10", 10.0])
def test_add_percent_coupon_rejects_bad_value(shop, value):
    with pytest.raises(ValidationError):
        shop.add_coupon("SAVE5", "percent", value)


def test_add_coupon_parses_min_subtotal(shop):
    result = shop.add_coupon("SAVE5", "fixed", "5", min_subtotal="20")
    assert result["min_subtotal"] == "20.00"


@pytest.mark.parametrize("value", ["x", "-1", "1.234", 1.5, True])
def test_add_coupon_rejects_bad_min_subtotal(shop, value):
    with pytest.raises(ValidationError):
        shop.add_coupon("SAVE5", "fixed", "5", min_subtotal=value)


def test_add_coupon_accepts_valid_expires(shop):
    result = shop.add_coupon("SAVE5", "fixed", "5", expires="2026-12-31")
    assert result["expires"] == "2026-12-31"


@pytest.mark.parametrize(
    "expires",
    ["2026-13-01", "2026-1-1", "26-12-31", "2026/12/31", "2026-12-32", "", 20261231, 123],
)
def test_add_coupon_rejects_bad_expires(shop, expires):
    with pytest.raises(ValidationError):
        shop.add_coupon("SAVE5", "fixed", "5", expires=expires)


# ---------------------------------------------------------------------------
# get_coupon
# ---------------------------------------------------------------------------

def test_get_coupon_unknown_raises_not_found(shop):
    with pytest.raises(NotFoundError):
        shop.get_coupon("NOPE1")


def test_get_coupon_normalizes_code(shop):
    shop.add_coupon("SAVE5", "fixed", "5")
    assert shop.get_coupon(" save5 ")["code"] == "SAVE5"


# ---------------------------------------------------------------------------
# 可用性辅助：_check_coupon_available（占用 / 过期 / 最低消费）
# ---------------------------------------------------------------------------

def test_check_coupon_available_returns_coupon(shop):
    shop.add_coupon("SAVE5", "fixed", "5")
    coupon = shop._check_coupon_available("SAVE5", Decimal("10.00"))
    assert coupon["code"] == "SAVE5"


def test_check_coupon_available_unknown_raises(shop):
    with pytest.raises(CouponError):
        shop._check_coupon_available("NOPE1", Decimal("10.00"))


def test_check_coupon_available_used_raises(shop):
    shop.add_coupon("SAVE5", "fixed", "5")
    shop._coupons["SAVE5"]["used_by"] = "O0001"
    with pytest.raises(CouponError):
        shop._check_coupon_available("SAVE5", Decimal("10.00"))


def test_check_coupon_available_expired_raises(shop):
    shop.add_coupon("SAVE5", "fixed", "5", expires="2026-01-14")
    with pytest.raises(CouponError):
        shop._check_coupon_available("SAVE5", Decimal("10.00"))


def test_check_coupon_available_expires_today_ok(shop):
    # 到期当天仍然可用
    shop.add_coupon("SAVE5", "fixed", "5", expires="2026-01-15")
    assert shop._check_coupon_available("SAVE5", Decimal("10.00"))["code"] == "SAVE5"


def test_check_coupon_available_min_subtotal_boundary(shop):
    shop.add_coupon("SAVE5", "fixed", "5", min_subtotal="20")
    with pytest.raises(CouponError):
        shop._check_coupon_available("SAVE5", Decimal("19.99"))
    assert shop._check_coupon_available("SAVE5", Decimal("20.00"))["code"] == "SAVE5"


# ---------------------------------------------------------------------------
# _is_expired / _coupon_discount
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "expires,expected",
    [(None, False), ("2026-01-14", True), ("2026-01-15", False), ("2026-01-16", False)],
)
def test_is_expired_by_date(shop, expires, expected):
    assert shop._is_expired({"expires": expires}) is expected


def test_coupon_discount_fixed_capped_at_subtotal(shop):
    coupon = {"kind": "fixed", "value": Decimal("5.00")}
    assert format_money(shop._coupon_discount(coupon, Decimal("3.00"))) == "3.00"
    assert format_money(shop._coupon_discount(coupon, Decimal("10.00"))) == "5.00"


def test_coupon_discount_percent_rounds_half_up(shop):
    coupon = {"kind": "percent", "value": 15}
    assert format_money(shop._coupon_discount(coupon, Decimal("27.00"))) == "4.05"
    # 15% * 0.10 = 0.015 -> 0.02
    assert format_money(shop._coupon_discount(coupon, Decimal("0.10"))) == "0.02"
