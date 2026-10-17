"""报表。"""

from datetime import date
from decimal import Decimal

from .errors import ValidationError
from .money import format_money

_SHIPPED_STATES = ("shipped", "delivered")


def _parse_date(value, field):
    if not isinstance(value, str) or len(value) != 10:
        raise ValidationError("{} 必须是 YYYY-MM-DD 字符串".format(field))
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValidationError("{} 不是合法日期: {!r}".format(field, value))


class ReportMixin:
    """报表相关方法。"""

    def sales_report(self, start, end):
        start_date = _parse_date(start, "start")
        end_date = _parse_date(end, "end")
        if start_date > end_date:
            raise ValidationError("start 不能晚于 end")

        orders_count = 0
        units = 0
        subtotal = Decimal("0.00")
        coupon_discount = Decimal("0.00")
        tax = Decimal("0.00")
        revenue = Decimal("0.00")
        by_category = {}

        for order, ship_date in self._shipped_orders():
            if ship_date < start_date or ship_date > end_date:
                continue
            pricing = order["pricing"]
            orders_count += 1
            subtotal += Decimal(pricing["subtotal"])
            coupon_discount += Decimal(pricing["coupon_discount"])
            tax += Decimal(pricing["tax"])
            revenue += Decimal(pricing["total"])
            for item in order["items"]:
                units += item["qty"]
            for line in pricing["lines"]:
                bucket = by_category.setdefault(
                    line["category"], {"units": 0, "net": Decimal("0.00")}
                )
                bucket["units"] += line["qty"]
                bucket["net"] += Decimal(line["net"])

        categories = [
            {
                "category": category,
                "units": data["units"],
                "net": format_money(data["net"]),
            }
            for category, data in by_category.items()
        ]
        categories.sort(key=lambda entry: (-Decimal(entry["net"]), entry["category"]))

        return {
            "orders": orders_count,
            "units": units,
            "subtotal": format_money(subtotal),
            "coupon_discount": format_money(coupon_discount),
            "tax": format_money(tax),
            "revenue": format_money(revenue),
            "by_category": categories,
        }

    def top_products(self, limit=5, start=None, end=None):
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise ValidationError("limit 必须是 int: {!r}".format(limit))
        if limit < 1:
            raise ValidationError("limit 必须大于等于 1")

        start_date = None if start is None else _parse_date(start, "start")
        end_date = None if end is None else _parse_date(end, "end")
        if start_date is not None and end_date is not None and start_date > end_date:
            raise ValidationError("start 不能晚于 end")

        units_by_sku = {}
        for order, ship_date in self._shipped_orders():
            if start_date is not None and ship_date < start_date:
                continue
            if end_date is not None and ship_date > end_date:
                continue
            for item in order["items"]:
                units_by_sku[item["sku"]] = units_by_sku.get(item["sku"], 0) + item["qty"]

        ranked = sorted(units_by_sku.items(), key=lambda kv: (-kv[1], kv[0]))
        return [{"sku": sku, "units": units} for sku, units in ranked[:limit]]

    def inventory_value(self):
        total = Decimal("0.00")
        for sku, product in self.products.items():
            on_hand = self.stock_levels[sku]["on_hand"]
            total += product["price"] * on_hand
        return format_money(total)

    # --- 内部辅助 -----------------------------------------------------
    def _shipped_orders(self):
        result = []
        for order_id in sorted(self.orders):
            order = self.orders[order_id]
            if order["status"] not in _SHIPPED_STATES:
                continue
            ship_date = self._ship_date(order)
            if ship_date is None:
                continue
            result.append((order, ship_date))
        return result

    @staticmethod
    def _ship_date(order):
        for event in order["events"]:
            if event["status"] == "shipped":
                return date.fromisoformat(event["at"][:10])
        return None
