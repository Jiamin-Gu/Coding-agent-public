"""报表：``ReportMixin``，销售报表、热销商品与库存价值。

金额一律来自订单的 ``pricing`` 快照：字符串先解析成 ``Decimal`` 再精确求和，
对外输出时用 ``format_money``。
"""

from datetime import date
from decimal import Decimal

from shopkit.errors import ValidationError
from shopkit.money import format_money

# 视为"已发货"的订单状态
_SHIPPED_STATUSES = ("shipped", "delivered")


class ReportMixin:
    """报表相关方法，供 :class:`~shopkit.shop.Shop` 混入。"""

    # --- 辅助 -----------------------------------------------------------

    @staticmethod
    def _parse_report_date(value, *, name="日期") -> str:
        """校验日期字符串：必须是正好 10 个字符的合法 ``YYYY-MM-DD``。"""
        if not isinstance(value, str):
            raise ValidationError(f"{name}必须是字符串，不能是 {type(value).__name__}")
        if len(value) != 10:
            raise ValidationError(f"{name}必须是 YYYY-MM-DD 格式：{value!r}")
        try:
            date.fromisoformat(value)
        except ValueError:
            raise ValidationError(f"{name}不是合法日期：{value!r}") from None
        return value

    @staticmethod
    def _shipped_date(order) -> str:
        """订单的发货日期：``status=='shipped'`` 事件的 ``at`` 前 10 个字符。"""
        for event in order["events"]:
            if event["status"] == "shipped":
                return event["at"][:10]
        return None

    def _shipped_orders(self, start=None, end=None) -> list:
        """返回发货日期落在 ``[start, end]``（含端点，两端可为 None）的已发货订单。"""
        result = []
        for order_id in sorted(self._orders):
            order = self._orders[order_id]
            if order["status"] not in _SHIPPED_STATUSES:
                continue
            shipped_date = self._shipped_date(order)
            if shipped_date is None:
                continue
            if start is not None and shipped_date < start:
                continue
            if end is not None and shipped_date > end:
                continue
            result.append(order)
        return result

    # --- 报表 -----------------------------------------------------------

    def sales_report(self, start, end) -> dict:
        """统计发货日期在 ``[start, end]`` 内的已发货订单。"""
        start = self._parse_report_date(start, name="start")
        end = self._parse_report_date(end, name="end")
        if start > end:
            raise ValidationError(f"start 不能晚于 end：{start!r} > {end!r}")

        orders = self._shipped_orders(start, end)

        units = 0
        subtotal = Decimal("0")
        coupon_discount = Decimal("0")
        tax = Decimal("0")
        revenue = Decimal("0")
        categories = {}

        for order in orders:
            pricing = order["pricing"]
            subtotal += Decimal(pricing["subtotal"])
            coupon_discount += Decimal(pricing["coupon_discount"])
            tax += Decimal(pricing["tax"])
            revenue += Decimal(pricing["total"])
            for line in pricing["lines"]:
                units += line["qty"]
                entry = categories.setdefault(line["category"], [0, Decimal("0")])
                entry[0] += line["qty"]
                entry[1] += Decimal(line["net"])

        by_category = [
            {"category": category, "units": data[0], "net": format_money(data[1])}
            for category, data in categories.items()
        ]
        # 先按 category 升序，再稳定地按 net 降序（Decimal 不能直接取负做 key）
        by_category.sort(key=lambda entry: entry["category"])
        by_category.sort(key=lambda entry: Decimal(entry["net"]), reverse=True)

        return {
            "orders": len(orders),
            "units": units,
            "subtotal": format_money(subtotal),
            "coupon_discount": format_money(coupon_discount),
            "tax": format_money(tax),
            "revenue": format_money(revenue),
            "by_category": by_category,
        }

    def top_products(self, limit=5, start=None, end=None) -> list:
        """已发货订单里各商品的件数排行。"""
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise ValidationError(f"limit 必须是整数，不能是 {type(limit).__name__}")
        if limit < 1:
            raise ValidationError(f"limit 必须 >= 1：{limit!r}")

        if start is not None:
            start = self._parse_report_date(start, name="start")
        if end is not None:
            end = self._parse_report_date(end, name="end")

        orders = self._shipped_orders(start, end)

        totals = {}
        for order in orders:
            for line in order["pricing"]["lines"]:
                totals[line["sku"]] = totals.get(line["sku"], 0) + line["qty"]

        ranking = [{"sku": sku, "units": units} for sku, units in totals.items()]
        ranking.sort(key=lambda entry: (-entry["units"], entry["sku"]))
        return ranking[:limit]

    def inventory_value(self) -> str:
        """所有商品（含下架）``on_hand × 当前价格`` 之和。"""
        total = Decimal("0")
        for sku, product in self._products.items():
            on_hand = self._stock[sku]["on_hand"]
            total += product["price"] * on_hand
        return format_money(total)
