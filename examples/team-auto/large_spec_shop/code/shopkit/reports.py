"""Reporting mixin: sales reports, top products and inventory value."""

from decimal import Decimal

from ._util import parse_date, require_int
from .errors import ValidationError
from .money import format_money

_ZERO = Decimal("0.00")
_SHIPPED = ("shipped", "delivered")


class ReportsMixin:
    """Aggregate reports over orders and stock (SPEC section 8)."""

    @staticmethod
    def _shipped_date(order):
        """Return the ``YYYY-MM-DD`` date the order was shipped, or ``None``."""
        for event in order["events"]:
            if event["status"] == "shipped":
                return event["at"][:10]
        return None

    def _shipped_orders(self, start, end):
        """Yield shipped/delivered orders whose ship date falls in ``[start, end]``.

        ``start`` and ``end`` are ``YYYY-MM-DD`` strings or ``None`` (no bound).
        """
        for oid in self._orders:
            order = self._orders[oid]
            if order["status"] not in _SHIPPED:
                continue
            shipped = self._shipped_date(order)
            if shipped is None:
                continue
            if start is not None and shipped < start:
                continue
            if end is not None and shipped > end:
                continue
            yield order

    def sales_report(self, start, end):
        """Aggregate a sales report for orders shipped within ``[start, end]``."""
        start = parse_date(start, "start")
        end = parse_date(end, "end")
        if start > end:
            raise ValidationError("start must not be after end")

        orders = 0
        units = 0
        subtotal = _ZERO
        coupon_discount = _ZERO
        tax = _ZERO
        revenue = _ZERO
        by_category = {}

        for order in self._shipped_orders(start, end):
            pricing = order["pricing"]
            if not pricing:
                continue
            orders += 1
            subtotal += Decimal(pricing["subtotal"])
            coupon_discount += Decimal(pricing["coupon_discount"])
            tax += Decimal(pricing["tax"])
            revenue += Decimal(pricing["total"])
            for line in pricing["lines"]:
                units += line["qty"]
                entry = by_category.get(line["category"])
                if entry is None:
                    entry = {"units": 0, "net": _ZERO}
                    by_category[line["category"]] = entry
                entry["units"] += line["qty"]
                entry["net"] += Decimal(line["net"])

        categories = [
            {
                "category": category,
                "units": data["units"],
                "net": format_money(data["net"]),
            }
            for category, data in by_category.items()
        ]
        categories.sort(key=lambda item: (-Decimal(item["net"]), item["category"]))

        return {
            "orders": orders,
            "units": units,
            "subtotal": format_money(subtotal),
            "coupon_discount": format_money(coupon_discount),
            "tax": format_money(tax),
            "revenue": format_money(revenue),
            "by_category": categories,
        }

    def top_products(self, limit=5, start=None, end=None):
        """Return the best selling skus (by units) among shipped orders."""
        limit = require_int(limit, "limit")
        if limit < 1:
            raise ValidationError("limit must be >= 1")
        start = None if start is None else parse_date(start, "start")
        end = None if end is None else parse_date(end, "end")

        totals = {}
        for order in self._shipped_orders(start, end):
            pricing = order["pricing"]
            if not pricing:
                continue
            for line in pricing["lines"]:
                totals[line["sku"]] = totals.get(line["sku"], 0) + line["qty"]

        ranked = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
        return [{"sku": sku, "units": u} for sku, u in ranked[:limit]]

    def inventory_value(self):
        """Return the total value of all stock at current prices."""
        total = _ZERO
        for sku, product in self._products.items():
            on_hand = self._stock.get(sku, {}).get("on_hand", 0)
            total += product["price"] * on_hand
        return format_money(total)
