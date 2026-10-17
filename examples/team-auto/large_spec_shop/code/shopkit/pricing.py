"""Pricing rules: tier prices, category discounts, tax and quotes."""

from decimal import Decimal

from ._util import norm_category, norm_code, require_int, validate_qty
from .errors import ValidationError
from .money import format_money, parse_money, round_money

_ZERO = Decimal("0.00")
_HUNDRED = Decimal("100")
_MAX_TAX_RATE = Decimal("30")


class PricingMixin:
    """Rule configuration and pure quote computation."""

    def set_tier_price(self, sku, min_qty, unit_price):
        """Set (or override) the unit price for buying at least ``min_qty``."""
        min_qty_norm = require_int(min_qty, "min_qty")
        if min_qty_norm < 2:
            raise ValidationError("min_qty must be >= 2")
        price_norm = parse_money(unit_price)
        if price_norm <= 0:
            raise ValidationError("tier unit_price must be > 0")
        self._product(sku)
        self._tiers.setdefault(sku, {})[min_qty_norm] = price_norm

    def clear_tier_prices(self, sku):
        """Remove every tier price configured for ``sku``."""
        self._product(sku)
        self._tiers.setdefault(sku, {}).clear()

    def set_category_discount(self, category, percent):
        """Set the discount percentage (0..90) for a category; 0 clears it."""
        category_norm = norm_category(category)
        percent_norm = require_int(percent, "percent")
        if not 0 <= percent_norm <= 90:
            raise ValidationError("percent must be in 0..90")
        self._cat_discount[category_norm] = percent_norm

    def set_tax_rate(self, category, rate):
        """Set the tax percentage (<= 30) for a category."""
        category_norm = norm_category(category)
        rate_norm = parse_money(rate)
        if rate_norm > _MAX_TAX_RATE:
            raise ValidationError("tax rate must be <= 30")
        self._tax[category_norm] = rate_norm

    def _merge_items(self, items, allow_empty):
        """Validate and merge shopping-list items, keeping first-seen order."""
        if not isinstance(items, list):
            raise ValidationError("items must be a list")
        if not items and not allow_empty:
            raise ValidationError("items must not be empty")

        quantities = {}
        order = []
        for item in items:
            if not isinstance(item, dict):
                raise ValidationError("each item must be a dict with sku and qty")
            if "sku" not in item or "qty" not in item:
                raise ValidationError("each item must have sku and qty")
            sku = item["sku"]
            if not isinstance(sku, str):
                raise ValidationError("sku must be a string")
            qty = validate_qty(item["qty"])
            if sku in quantities:
                quantities[sku] += qty
            else:
                quantities[sku] = qty
                order.append(sku)

        for sku in order:
            product = self._product(sku)
            if not product["active"]:
                raise ValidationError("product is not active")

        return [{"sku": sku, "qty": quantities[sku]} for sku in order]

    def quote(self, items, coupon=None):
        """Compute a price quote.  Pure: no stock checks and no side effects."""
        merged = self._merge_items(items, allow_empty=False)

        if coupon is None:
            coupon_code = None
        else:
            coupon_code = norm_code(coupon)

        rows = []
        subtotal = _ZERO
        for item in merged:
            sku = item["sku"]
            qty = item["qty"]
            product = self._products[sku]
            category = product["category"]

            unit_price = product["price"]
            tiers = self._tiers.get(sku)
            if tiers:
                applicable = [m for m in tiers if m <= qty]
                if applicable:
                    unit_price = tiers[max(applicable)]

            line_total = round_money(unit_price * qty)
            percent = self._cat_discount.get(category, 0)
            discount = round_money(line_total * Decimal(percent) / _HUNDRED)
            net = line_total - discount

            rows.append(
                {
                    "sku": sku,
                    "category": category,
                    "qty": qty,
                    "unit_price": unit_price,
                    "line_total": line_total,
                    "discount": discount,
                    "net": net,
                }
            )
            subtotal += net

        coupon_discount = _ZERO
        if coupon_code is not None:
            coupon_obj = self._check_coupon(coupon_code, subtotal)
            coupon_discount = self._coupon_amount(coupon_obj, subtotal)

        shares = []
        allocated = _ZERO
        last = len(rows) - 1
        for index, row in enumerate(rows):
            if coupon_code is None:
                share = _ZERO
            elif index < last:
                share = round_money(coupon_discount * row["net"] / subtotal)
            else:
                share = coupon_discount - allocated
            shares.append(share)
            allocated += share

        total_tax = _ZERO
        lines = []
        for row, share in zip(rows, shares):
            tax_rate = self._tax.get(row["category"], _ZERO)
            line_tax = round_money((row["net"] - share) * tax_rate / _HUNDRED)
            total_tax += line_tax
            lines.append(
                {
                    "sku": row["sku"],
                    "category": row["category"],
                    "qty": row["qty"],
                    "unit_price": format_money(row["unit_price"]),
                    "line_total": format_money(row["line_total"]),
                    "discount": format_money(row["discount"]),
                    "net": format_money(row["net"]),
                    "coupon_share": format_money(share),
                    "tax": format_money(line_tax),
                }
            )

        total = subtotal - coupon_discount + total_tax
        return {
            "lines": lines,
            "subtotal": format_money(subtotal),
            "coupon": coupon_code,
            "coupon_discount": format_money(coupon_discount),
            "tax": format_money(total_tax),
            "total": format_money(total),
        }
