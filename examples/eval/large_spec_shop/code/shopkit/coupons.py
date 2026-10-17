"""优惠券。"""

from datetime import date

from .errors import NotFoundError, ValidationError
from .money import format_money, parse_money
from ._util import normalize_coupon_code, validate_coupon_code

_FIXED = "fixed"
_PERCENT = "percent"


class CouponMixin:
    """优惠券相关方法。"""

    def add_coupon(self, code, kind, value, min_subtotal="0", expires=None):
        clean_code = validate_coupon_code(code)

        if kind not in (_FIXED, _PERCENT):
            raise ValidationError("未知的优惠券类型: {!r}".format(kind))

        if kind == _FIXED:
            clean_value = parse_money(value)
            if clean_value <= 0:
                raise ValidationError("固定金额必须大于 0")
        else:
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValidationError("百分比必须是 int: {!r}".format(value))
            if value < 1 or value > 100:
                raise ValidationError("百分比必须在 1~100 之间")
            clean_value = value

        clean_min_subtotal = parse_money(min_subtotal)
        clean_expires = self._validate_expires(expires)

        if clean_code in self.coupons:
            raise ValidationError("优惠券已存在: {!r}".format(clean_code))

        self.coupons[clean_code] = {
            "code": clean_code,
            "kind": kind,
            "value": clean_value,
            "min_subtotal": clean_min_subtotal,
            "expires": clean_expires,
            "used_by": None,
        }
        return self.get_coupon(clean_code)

    def get_coupon(self, code):
        normalized = normalize_coupon_code(code)
        coupon = self.coupons.get(normalized)
        if coupon is None:
            raise NotFoundError("优惠券不存在: {!r}".format(code))
        return self._coupon_view(coupon)

    @staticmethod
    def _validate_expires(expires):
        if expires is None:
            return None
        if not isinstance(expires, str) or len(expires) != 10:
            raise ValidationError("expires 必须是 YYYY-MM-DD 字符串")
        try:
            date.fromisoformat(expires)
        except ValueError:
            raise ValidationError("expires 不是合法日期: {!r}".format(expires))
        return expires

    @staticmethod
    def _coupon_view(coupon):
        if coupon["kind"] == _FIXED:
            value = format_money(coupon["value"])
        else:
            value = coupon["value"]
        return {
            "code": coupon["code"],
            "kind": coupon["kind"],
            "value": value,
            "min_subtotal": format_money(coupon["min_subtotal"]),
            "expires": coupon["expires"],
            "used_by": coupon["used_by"],
        }
