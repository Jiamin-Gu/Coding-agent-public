"""Coupon rules: fixed-amount and percentage coupons."""

from datetime import date
from decimal import Decimal

from ._util import norm_code, parse_date, require_int, validate_code_format
from .errors import CouponError, NotFoundError, ValidationError
from .money import format_money, parse_money, round_money

_ZERO = Decimal("0.00")
_HUNDRED = Decimal("100")
_KINDS = ("fixed", "percent")


class CouponMixin:
    """Coupon creation, lookup and availability checks."""

    def add_coupon(self, code, kind, value, min_subtotal="0", expires=None):
        """Register a new coupon and return it via :meth:`get_coupon`."""
        code_norm = validate_code_format(norm_code(code))
        if code_norm in self._coupons:
            raise ValidationError("coupon code already exists")
        if kind not in _KINDS:
            raise ValidationError("kind must be 'fixed' or 'percent'")
        if kind == "fixed":
            amount = parse_money(value)
            if amount <= 0:
                raise ValidationError("fixed coupon value must be > 0")
        else:
            amount = require_int(value, "value")
            if not 1 <= amount <= 100:
                raise ValidationError("percent coupon value must be 1..100")
        min_subtotal_norm = parse_money(min_subtotal)
        expires_norm = None if expires is None else parse_date(expires, "expires")

        self._coupons[code_norm] = {
            "code": code_norm,
            "kind": kind,
            "value": amount,
            "min_subtotal": min_subtotal_norm,
            "expires": expires_norm,
            "used_by": None,
        }
        return self.get_coupon(code_norm)

    def get_coupon(self, code):
        """Return a public view of a coupon; missing codes raise NotFoundError."""
        coupon = self._coupons.get(norm_code(code))
        if coupon is None:
            raise NotFoundError("coupon not found")
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

    def _check_coupon(self, code_norm, subtotal):
        """Return the internal coupon if usable for ``subtotal`` else CouponError."""
        coupon = self._coupons.get(code_norm)
        if coupon is None:
            raise CouponError("coupon does not exist")
        if coupon["used_by"] is not None:
            raise CouponError("coupon is already used")
        expires = coupon["expires"]
        if expires is not None and self._clock().date() > date.fromisoformat(expires):
            raise CouponError("coupon is expired")
        if subtotal < coupon["min_subtotal"]:
            raise CouponError("subtotal is below the coupon minimum")
        return coupon

    def _coupon_amount(self, coupon, subtotal):
        """Discount amount produced by ``coupon`` for the given ``subtotal``."""
        if coupon["kind"] == "fixed":
            return min(coupon["value"], subtotal)
        return round_money(subtotal * Decimal(coupon["value"]) / _HUNDRED)
