from decimal import Decimal

from .catalog import PRODUCTS


def buy_one_get_one(lines, sku):
    discount = Decimal("0")
    for line in lines:
        if line["sku"] == sku:
            discount += Decimal(PRODUCTS[sku]["price"]) * (line["qty"] // 2)
    return discount


def category_percent(lines, category, percent):
    total = sum((Decimal(PRODUCTS[l["sku"]]["price"]) * l["qty"]
                 for l in lines if PRODUCTS[l["sku"]]["category"] == category), Decimal("0"))
    return total * Decimal(percent) / 100
