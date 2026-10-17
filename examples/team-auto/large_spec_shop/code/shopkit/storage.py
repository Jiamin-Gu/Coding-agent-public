"""Persistence helpers: serialise/restore the whole ``Shop`` state as JSON."""

import json
import os

from .errors import NotFoundError
from .money import format_money, parse_money


def dump_state(shop):
    """Return a JSON-serialisable snapshot of every piece of ``shop`` state."""
    products = {}
    for sku, product in shop._products.items():
        products[sku] = {
            "name": product["name"],
            "price": format_money(product["price"]),
            "category": product["category"],
            "active": product["active"],
        }

    stock = {
        sku: {
            "on_hand": state["on_hand"],
            "reserved": state["reserved"],
            "reorder_level": state["reorder_level"],
        }
        for sku, state in shop._stock.items()
    }

    logs = {sku: [dict(entry) for entry in entries] for sku, entries in shop._logs.items()}

    tiers = {
        sku: {str(min_qty): format_money(price) for min_qty, price in levels.items()}
        for sku, levels in shop._tiers.items()
    }

    coupons = {}
    for code, coupon in shop._coupons.items():
        if coupon["kind"] == "fixed":
            value = format_money(coupon["value"])
        else:
            value = coupon["value"]
        coupons[code] = {
            "code": coupon["code"],
            "kind": coupon["kind"],
            "value": value,
            "min_subtotal": format_money(coupon["min_subtotal"]),
            "expires": coupon["expires"],
            "used_by": coupon["used_by"],
        }

    tax = {category: format_money(rate) for category, rate in shop._tax.items()}

    return {
        "products": products,
        "stock": stock,
        "logs": logs,
        "tiers": tiers,
        "category_discounts": dict(shop._cat_discount),
        "tax": tax,
        "coupons": coupons,
        "orders": shop._orders,
        "order_seq": shop._order_seq,
    }


def load(cls, path, clock=None):
    """Read an archive written by :meth:`Shop.save` and restore a new ``cls``."""
    if not os.path.isfile(path):
        raise NotFoundError(f"archive {path!r} not found")
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)

    shop = cls(clock=clock)
    _restore(shop, data)
    return shop


def _restore(shop, data):
    """Populate ``shop`` from the decoded ``data`` snapshot."""
    for sku, product in data["products"].items():
        shop._products[sku] = {
            "sku": sku,
            "name": product["name"],
            "price": parse_money(product["price"]),
            "category": product["category"],
            "active": product["active"],
        }

    for sku, state in data["stock"].items():
        shop._stock[sku] = {
            "on_hand": int(state["on_hand"]),
            "reserved": int(state["reserved"]),
            "reorder_level": int(state["reorder_level"]),
        }

    for sku, entries in data["logs"].items():
        shop._logs[sku] = [
            {"at": entry["at"], "change": int(entry["change"]), "reason": entry["reason"]}
            for entry in entries
        ]

    for sku, levels in data["tiers"].items():
        shop._tiers[sku] = {int(min_qty): parse_money(price) for min_qty, price in levels.items()}

    shop._cat_discount = {
        category: int(percent) for category, percent in data["category_discounts"].items()
    }

    shop._tax = {category: parse_money(rate) for category, rate in data["tax"].items()}

    coupons = {}
    for code, coupon in data["coupons"].items():
        if coupon["kind"] == "fixed":
            value = parse_money(coupon["value"])
        else:
            value = int(coupon["value"])
        coupons[code] = {
            "code": coupon["code"],
            "kind": coupon["kind"],
            "value": value,
            "min_subtotal": parse_money(coupon["min_subtotal"]),
            "expires": coupon["expires"],
            "used_by": coupon["used_by"],
        }
    shop._coupons = coupons

    shop._orders = data["orders"]
    shop._order_seq = int(data["order_seq"])
