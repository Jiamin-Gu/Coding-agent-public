import math
from decimal import Decimal

from .catalog import PRODUCTS

FREE_THRESHOLD = Decimal("99")


def shipping_fee(lines, merchandise_total):
    if merchandise_total >= FREE_THRESHOLD:
        return Decimal("0")
    weight = sum(Decimal(str(PRODUCTS[l["sku"]]["weight"])) * l["qty"] for l in lines)
    extra = max(Decimal("0"), weight - 3)
    return Decimal("8") + Decimal("2") * math.ceil(extra)
