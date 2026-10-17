"""定价规则与报价计算。"""

from datetime import date
from decimal import Decimal

from .errors import (
    CouponError,
    NotFoundError,
    ValidationError,
)
from .money import format_money, parse_money, round_money
from ._util import normalize_coupon_code, normalize_category


class PricingMixin:
    """阶梯价、类别折扣、税率与报价。"""

    # --- 规则设置 -----------------------------------------------------
    def set_tier_price(self, sku, min_qty, unit_price):
        if isinstance(min_qty, bool) or not isinstance(min_qty, int):
            raise ValidationError("min_qty 必须是 int: {!r}".format(min_qty))
        if min_qty < 2:
            raise ValidationError("min_qty 必须大于等于 2")
        clean_price = parse_money(unit_price)
        if clean_price <= 0:
            raise ValidationError("阶梯价必须大于 0")
        if sku not in self.products:
            raise NotFoundError("商品不存在: {!r}".format(sku))
        self.tiers.setdefault(sku, {})[min_qty] = clean_price
        return None

    def clear_tier_prices(self, sku):
        if sku not in self.products:
            raise NotFoundError("商品不存在: {!r}".format(sku))
        self.tiers[sku] = {}
        return None

    def set_category_discount(self, category, percent):
        clean_category = normalize_category(category)
        if isinstance(percent, bool) or not isinstance(percent, int):
            raise ValidationError("折扣百分比必须是 int: {!r}".format(percent))
        if percent < 0 or percent > 90:
            raise ValidationError("折扣百分比必须在 0~90 之间")
        if percent == 0:
            self.category_discounts.pop(clean_category, None)
        else:
            self.category_discounts[clean_category] = percent
        return None

    def set_tax_rate(self, category, rate):
        clean_category = normalize_category(category)
        clean_rate = parse_money(rate)
        if clean_rate > 30:
            raise ValidationError("税率不能超过 30")
        self.tax_rates[clean_category] = clean_rate
        return None

    # --- 报价 ---------------------------------------------------------
    def quote(self, items, coupon=None):
        merged = self._normalize_items(items, allow_empty=False)
        if coupon is not None and not isinstance(coupon, str):
            raise ValidationError("优惠券代码必须是字符串或 None")
        return self._compute_pricing(merged, coupon)

    # --- 内部辅助 -----------------------------------------------------
    def _normalize_items(self, items, allow_empty):
        if not isinstance(items, list):
            raise ValidationError("items 必须是列表")
        if not items:
            if allow_empty:
                return []
            raise ValidationError("items 不能为空")

        merged = {}
        order = []
        for element in items:
            if not isinstance(element, dict):
                raise ValidationError("items 的元素必须是 dict")
            if "sku" not in element or "qty" not in element:
                raise ValidationError("items 的元素必须包含 sku 和 qty")
            sku = element["sku"]
            qty = element["qty"]
            if not isinstance(sku, str):
                raise ValidationError("sku 必须是字符串")
            if isinstance(qty, bool) or not isinstance(qty, int) or qty < 1:
                raise ValidationError("qty 必须是 >= 1 的 int")
            if sku not in merged:
                merged[sku] = 0
                order.append(sku)
            merged[sku] += qty
        return [{"sku": sku, "qty": merged[sku]} for sku in order]

    def _compute_pricing(self, merged, coupon_code):
        lines = []
        for item in merged:
            sku = item["sku"]
            qty = item["qty"]
            product = self.products.get(sku)
            if product is None:
                raise NotFoundError("商品不存在: {!r}".format(sku))
            if not product["active"]:
                raise ValidationError("商品已下架: {!r}".format(sku))

            unit_price = self._resolve_unit_price(sku, qty, product["price"])
            line_total = unit_price * qty

            percent = self.category_discounts.get(product["category"], 0)
            discount = round_money(line_total * Decimal(percent) / 100)
            net = line_total - discount

            lines.append(
                {
                    "sku": sku,
                    "category": product["category"],
                    "qty": qty,
                    "unit_price": unit_price,
                    "line_total": line_total,
                    "discount": discount,
                    "net": net,
                    "coupon_share": Decimal("0.00"),
                    "tax": Decimal("0.00"),
                }
            )

        subtotal = sum((line["net"] for line in lines), Decimal("0.00"))

        coupon_discount, normalized_coupon = self._resolve_coupon(
            coupon_code, subtotal
        )

        self._allocate_coupon(lines, coupon_discount, subtotal)

        tax_total = Decimal("0.00")
        for line in lines:
            rate = self.tax_rates.get(line["category"], Decimal("0.00"))
            tax = round_money((line["net"] - line["coupon_share"]) * rate / 100)
            line["tax"] = tax
            tax_total += tax

        total = subtotal - coupon_discount + tax_total

        return {
            "lines": [self._format_line(line) for line in lines],
            "subtotal": format_money(subtotal),
            "coupon": normalized_coupon,
            "coupon_discount": format_money(coupon_discount),
            "tax": format_money(tax_total),
            "total": format_money(total),
        }

    def _resolve_unit_price(self, sku, qty, base_price):
        tiers = self.tiers.get(sku) or {}
        best_min_qty = None
        for min_qty in tiers:
            if qty >= min_qty and (best_min_qty is None or min_qty > best_min_qty):
                best_min_qty = min_qty
        if best_min_qty is None:
            return base_price
        return tiers[best_min_qty]

    def _resolve_coupon(self, coupon_code, subtotal):
        if coupon_code is None:
            return Decimal("0.00"), None

        normalized = normalize_coupon_code(coupon_code)
        coupon = self.coupons.get(normalized)
        if coupon is None:
            raise CouponError("优惠券不存在: {!r}".format(coupon_code))
        if coupon["used_by"] is not None:
            raise CouponError("优惠券已被使用: {!r}".format(normalized))
        if self._coupon_expired(coupon):
            raise CouponError("优惠券已过期: {!r}".format(normalized))
        if subtotal < coupon["min_subtotal"]:
            raise CouponError("未达到最低消费: {!r}".format(normalized))

        if coupon["kind"] == "fixed":
            discount = min(coupon["value"], subtotal)
        else:
            discount = round_money(subtotal * Decimal(coupon["value"]) / 100)
        return discount, normalized

    def _coupon_expired(self, coupon):
        expires = coupon["expires"]
        if expires is None:
            return False
        return self._clock().date() > date.fromisoformat(expires)

    @staticmethod
    def _allocate_coupon(lines, coupon_discount, subtotal):
        if coupon_discount == 0 or not lines:
            for line in lines:
                line["coupon_share"] = Decimal("0.00")
            return
        if subtotal == 0:
            for line in lines:
                line["coupon_share"] = Decimal("0.00")
            return

        allocated = Decimal("0.00")
        for index, line in enumerate(lines):
            if index == len(lines) - 1:
                share = coupon_discount - allocated
            else:
                share = round_money(coupon_discount * line["net"] / subtotal)
                allocated += share
            line["coupon_share"] = share

    @staticmethod
    def _format_line(line):
        return {
            "sku": line["sku"],
            "category": line["category"],
            "qty": line["qty"],
            "unit_price": format_money(line["unit_price"]),
            "line_total": format_money(line["line_total"]),
            "discount": format_money(line["discount"]),
            "net": format_money(line["net"]),
            "coupon_share": format_money(line["coupon_share"]),
            "tax": format_money(line["tax"]),
        }
