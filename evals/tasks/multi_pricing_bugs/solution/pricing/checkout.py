from decimal import ROUND_HALF_UP, Decimal

from . import promotions
from .catalog import PRODUCTS
from .shipping import shipping_fee
from .tax import tax_for

PROMOS = [("bogo", "banana"), ("category", "dairy", 10)]


def subtotal(lines):
    return sum((Decimal(PRODUCTS[l["sku"]]["price"]) * l["qty"] for l in lines), Decimal("0"))


def discounts(lines):
    total = Decimal("0")
    for promo in PROMOS:
        if promo[0] == "bogo":
            total += promotions.buy_one_get_one(lines, promo[1])
        elif promo[0] == "category":
            total += promotions.category_percent(lines, promo[1], promo[2])
    return total


def _cents(x):
    return Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def checkout(lines, region):
    sub = subtotal(lines)
    disc = discounts(lines)
    merch = sub - disc
    tax = tax_for(merch, region)
    ship = shipping_fee(lines, merch)
    total = merch + tax + ship
    return {"subtotal": _cents(sub), "discount": _cents(disc), "merchandise": _cents(merch),
            "tax": _cents(tax), "shipping": _cents(ship), "total": _cents(total)}
