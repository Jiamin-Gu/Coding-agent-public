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
    """结算。lines 形如 [{"sku": "apple", "qty": 2}]。

    返回各项金额（保留两位小数的 Decimal，四舍五入）：
    subtotal 原价合计；discount 优惠；merchandise 打折后的商品金额；
    tax 按打折后的商品金额计税；shipping 运费（免运费门槛也按打折后金额判断）；total 应付总额。

    舍入规则：优惠和打折后金额在计算过程中保持完整精度，不提前四舍五入；
    税额按 tax_for 的规则单独四舍五入到分；
    total = 完整精度的打折后金额 + 税额 + 运费；所有返回值最后统一四舍五入到分。
    """
    sub = subtotal(lines)
    disc = discounts(lines)
    merch = sub - disc
    tax = tax_for(merch, region)
    ship = shipping_fee(lines, merch)
    total = merch + tax + ship
    return {"subtotal": _cents(sub), "discount": _cents(disc), "merchandise": _cents(merch),
            "tax": _cents(tax), "shipping": _cents(ship), "total": _cents(total)}
