"""优惠券：``CouponMixin``，负责优惠券的登记、查询与可用性/折扣计算。"""

import re
from datetime import date

from shopkit.errors import CouponError, NotFoundError, ValidationError
from shopkit.money import format_money, parse_money, round_money

_CODE_RE = re.compile(r"[A-Z0-9]{3,16}")


class CouponMixin:
    """优惠券相关的公开 API 与内部辅助。"""

    def add_coupon(self, code, kind, value, min_subtotal="0", expires=None):
        """登记一张优惠券，返回 `get_coupon` 的结果。"""
        code = self._normalize_code(code)
        if not _CODE_RE.fullmatch(code):
            raise ValidationError(f"优惠券代码格式不合法：{code!r}")
        if code in self._coupons:
            raise ValidationError(f"优惠券已存在：{code!r}")

        if kind not in ("fixed", "percent"):
            raise ValidationError(f"优惠券类型不合法：{kind!r}")

        if kind == "fixed":
            amount = parse_money(value)
            if amount <= 0:
                raise ValidationError("fixed 优惠券金额必须大于 0")
        else:
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValidationError("percent 优惠券折扣必须是 int")
            if not 1 <= value <= 100:
                raise ValidationError("percent 优惠券折扣必须在 1~100 之间")
            amount = value

        min_amount = parse_money(min_subtotal)

        if expires is not None:
            if not isinstance(expires, str) or len(expires) != 10:
                raise ValidationError(f"到期日期不合法：{expires!r}")
            try:
                date.fromisoformat(expires)
            except ValueError:
                raise ValidationError(f"到期日期不合法：{expires!r}") from None

        self._coupons[code] = {
            "code": code,
            "kind": kind,
            "value": amount,
            "min_subtotal": min_amount,
            "expires": expires,
            "used_by": None,
        }
        return self.get_coupon(code)

    def get_coupon(self, code):
        """按代码查询优惠券，返回对外格式。"""
        code = self._normalize_code(code)
        coupon = self._coupons.get(code)
        if coupon is None:
            raise NotFoundError(f"优惠券不存在：{code!r}")

        if coupon["kind"] == "fixed":
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

    def _normalize_code(self, value):
        """优惠券代码：非 str → ValidationError；返回 strip + upper。"""
        if not isinstance(value, str):
            raise ValidationError(f"优惠券代码必须是字符串，不能是 {type(value).__name__}")
        return value.strip().upper()

    def _is_expired(self, coupon):
        """是否已过期：expires 非 None 且 clock() 的日期晚于它（到期当天可用）。"""
        expires = coupon["expires"]
        if expires is None:
            return False
        return self._clock().date().isoformat() > expires

    def _check_coupon_available(self, code, subtotal):
        """检查优惠券可用性，通过则返回内部 coupon dict，否则 CouponError。"""
        code = self._normalize_code(code)
        coupon = self._coupons.get(code)
        if coupon is None:
            raise CouponError(f"优惠券不存在：{code!r}")
        if coupon["used_by"] is not None:
            raise CouponError(f"优惠券已被使用：{code!r}")
        if self._is_expired(coupon):
            raise CouponError(f"优惠券已过期：{code!r}")
        if subtotal < coupon["min_subtotal"]:
            raise CouponError(f"未达到最低消费：{code!r}")
        return coupon

    def _coupon_discount(self, coupon, subtotal):
        """计算优惠券折扣金额（Decimal）。"""
        if coupon["kind"] == "fixed":
            return min(coupon["value"], subtotal)
        return round_money(subtotal * coupon["value"] / 100)
