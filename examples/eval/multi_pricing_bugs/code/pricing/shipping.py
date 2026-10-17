from decimal import ROUND_CEILING, Decimal

from .catalog import PRODUCTS

FREE_THRESHOLD = Decimal("99")


def shipping_fee(lines, merchandise_total):
    """运费：商品金额（打折后）满 99 元免运费；否则基础运费 8 元，
    总重量超过 3kg 的部分每 kg 加收 2 元，不足 1kg 按 1kg 计算。"""
    if merchandise_total >= FREE_THRESHOLD:
        return Decimal("0")
    weight = sum((Decimal(str(PRODUCTS[l["sku"]]["weight"])) * l["qty"] for l in lines),
                 Decimal("0"))
    extra = weight - Decimal("3")
    if extra <= 0:
        return Decimal("8")
    return Decimal("8") + Decimal("2") * extra.to_integral_value(rounding=ROUND_CEILING)
