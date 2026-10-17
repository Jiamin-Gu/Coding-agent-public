from decimal import Decimal

from .catalog import PRODUCTS


def buy_one_get_one(lines, sku):
    """买一送一：同一商品每买两件，其中一件免费（买 3 件付 2 件的钱）。返回优惠金额。"""
    discount = Decimal("0")
    for line in lines:
        if line["sku"] == sku:
            free = line["qty"] // 2
            discount += Decimal(PRODUCTS[sku]["price"]) * free
    return discount


def category_percent(lines, category, percent):
    """某个品类打折，percent=10 表示减 10%。返回优惠金额。"""
    total = sum((Decimal(PRODUCTS[l["sku"]]["price"]) * l["qty"]
                 for l in lines if PRODUCTS[l["sku"]]["category"] == category), Decimal("0"))
    return total * Decimal(percent) / 100
