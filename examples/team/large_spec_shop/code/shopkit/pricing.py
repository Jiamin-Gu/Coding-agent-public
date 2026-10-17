"""定价：阶梯价、类别折扣、税率与报价（``PricingMixin``）。

金额内部一律用 ``Decimal``，对外输出用 ``format_money`` 的字符串。
``quote`` 只做计算，不检查库存、不产生任何副作用。
"""

from decimal import Decimal

from shopkit.errors import NotFoundError, ValidationError
from shopkit.money import format_money, parse_money, round_money

_ZERO = Decimal("0.00")


class PricingMixin:
    """定价规则设置与报价计算，供 :class:`~shopkit.shop.Shop` 混入。"""

    # --- 辅助 -----------------------------------------------------------

    @staticmethod
    def _validate_qty(value):
        """qty 必须是 int（非 bool）且 >= 1。"""
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValidationError(f"数量必须是 >=1 的整数：{value!r}")

    def _tier_unit_price(self, sku, qty, default):
        """返回该商品在给定数量下适用的单价（选 min_qty 最大的匹配阶梯）。"""
        tiers = self._tiers.get(sku)
        if not tiers:
            return default
        candidates = [min_qty for min_qty in tiers if qty >= min_qty]
        if not candidates:
            return default
        return tiers[max(candidates)]

    # --- 公开接口：规则设置 ---------------------------------------------

    def set_tier_price(self, sku, min_qty, unit_price):
        """设置阶梯价；同一 sku 同一 min_qty 覆盖。"""
        if isinstance(min_qty, bool) or not isinstance(min_qty, int) or min_qty < 2:
            raise ValidationError(f"阶梯起始数量必须是 >=2 的整数：{min_qty!r}")
        price = parse_money(unit_price)
        if price <= 0:
            raise ValidationError("阶梯单价必须大于 0")

        self._get_product(sku)
        self._tiers.setdefault(sku, {})[min_qty] = price

    def clear_tier_prices(self, sku):
        """删除该 sku 的全部阶梯价。"""
        self._get_product(sku)
        self._tiers.pop(sku, None)

    def set_category_discount(self, category, percent):
        """设置类别折扣（0~90，0 表示取消）。"""
        if isinstance(percent, bool) or not isinstance(percent, int) or not 0 <= percent <= 90:
            raise ValidationError(f"类别折扣必须是 0~90 的整数：{percent!r}")
        category = self._normalize_category(category)
        self._discounts[category] = percent

    def set_tax_rate(self, category, rate):
        """设置类别税率（百分比，非负、最多两位小数且 <=30）。"""
        clean_rate = parse_money(rate)
        if clean_rate > 30:
            raise ValidationError(f"税率不能超过 30：{rate!r}")
        category = self._normalize_category(category)
        self._tax_rates[category] = clean_rate

    # --- 公开接口：报价 -------------------------------------------------

    def quote(self, items, coupon=None):
        """给购物清单报价，不检查库存、无副作用。"""
        merged = self._merge_items(items)

        normalized_coupon = None
        if coupon is not None:
            if not isinstance(coupon, str):
                raise ValidationError(f"优惠券代码必须是字符串，不能是 {type(coupon).__name__}")
            normalized_coupon = self._normalize_code(coupon)

        # 解析商品并校验存在 / 上架，同时合并后的行顺序保持不变
        resolved = []
        for sku, qty in merged:
            product = self._get_product(sku)
            if not product["active"]:
                raise ValidationError(f"商品已下架：{sku!r}")
            resolved.append((product, qty))

        # 逐行计算单价、行金额、类别折扣、折后金额
        lines = []
        subtotal = _ZERO
        for product, qty in resolved:
            unit_price = self._tier_unit_price(product["sku"], qty, product["price"])
            line_total = unit_price * qty
            discount_pct = self._discounts.get(product["category"], 0)
            discount = round_money(line_total * discount_pct / 100)
            net = line_total - discount
            subtotal += net
            lines.append(
                {
                    "product": product,
                    "qty": qty,
                    "unit_price": unit_price,
                    "line_total": line_total,
                    "discount": discount,
                    "net": net,
                }
            )

        # 优惠券折扣
        coupon_discount = _ZERO
        if normalized_coupon is not None:
            available = self._check_coupon_available(normalized_coupon, subtotal)
            coupon_discount = self._coupon_discount(available, subtotal)

        # 优惠券分摊：除最后一行外按比例，最后一行补差
        shares = [Decimal("0.00")] * len(lines)
        if coupon_discount > 0:
            allocated = _ZERO
            last = len(lines) - 1
            for i, line in enumerate(lines):
                if i == last:
                    shares[i] = coupon_discount - allocated
                else:
                    share = round_money(coupon_discount * line["net"] / subtotal)
                    shares[i] = share
                    allocated += share

        # 税：每行 (net - coupon_share) × 税率
        tax_total = _ZERO
        result_lines = []
        for i, line in enumerate(lines):
            category = line["product"]["category"]
            rate = self._tax_rates.get(category, _ZERO)
            tax = round_money((line["net"] - shares[i]) * rate / 100)
            tax_total += tax
            result_lines.append(
                {
                    "sku": line["product"]["sku"],
                    "category": category,
                    "qty": line["qty"],
                    "unit_price": format_money(line["unit_price"]),
                    "line_total": format_money(line["line_total"]),
                    "discount": format_money(line["discount"]),
                    "net": format_money(line["net"]),
                    "coupon_share": format_money(shares[i]),
                    "tax": format_money(tax),
                }
            )

        total = subtotal - coupon_discount + tax_total
        return {
            "lines": result_lines,
            "subtotal": format_money(subtotal),
            "coupon": normalized_coupon,
            "coupon_discount": format_money(coupon_discount),
            "tax": format_money(tax_total),
            "total": format_money(total),
        }

    # --- 内部：解析/合并清单 -------------------------------------------

    def _merge_items(self, items):
        """校验 items 结构并合并重复 sku，保留首次出现的位置。"""
        if not isinstance(items, list) or len(items) == 0:
            raise ValidationError("items 必须是非空列表")

        order = []
        quantities = {}
        for item in items:
            if not isinstance(item, dict) or set(item.keys()) != {"sku", "qty"}:
                raise ValidationError(f"清单元素必须是 {{'sku','qty'}}：{item!r}")
            sku = item["sku"]
            if not isinstance(sku, str):
                raise ValidationError(f"sku 必须是字符串，不能是 {type(sku).__name__}")
            self._validate_qty(item["qty"])
            if sku not in quantities:
                order.append(sku)
                quantities[sku] = 0
            quantities[sku] += item["qty"]
        return [(sku, quantities[sku]) for sku in order]
