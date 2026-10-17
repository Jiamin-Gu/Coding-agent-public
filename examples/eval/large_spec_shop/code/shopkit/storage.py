"""持久化。"""

import json
import os
import tempfile
from decimal import Decimal

from .errors import NotFoundError
from .money import format_money


class StorageMixin:
    """保存与加载全部状态。"""

    def save(self, path):
        state = self._to_state()
        directory = os.path.dirname(os.path.abspath(path))
        fd, tmp_path = tempfile.mkstemp(
            dir=directory, prefix=".shopkit-", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(state, handle, ensure_ascii=False, indent=2)
            os.replace(tmp_path, path)
        except BaseException:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise

    @classmethod
    def load(cls, path, clock=None):
        if not os.path.exists(path):
            raise NotFoundError("存档文件不存在: {!r}".format(path))
        with open(path, "r", encoding="utf-8") as handle:
            state = json.load(handle)

        shop = cls(clock=clock)
        shop._from_state(state)
        return shop

    # --- 内部辅助 -----------------------------------------------------
    def _to_state(self):
        products = {}
        for sku, product in self.products.items():
            products[sku] = {
                "sku": product["sku"],
                "name": product["name"],
                "price": format_money(product["price"]),
                "category": product["category"],
                "active": product["active"],
            }

        tiers = {
            sku: {str(min_qty): format_money(price) for min_qty, price in mapping.items()}
            for sku, mapping in self.tiers.items()
        }

        tax_rates = {
            category: format_money(rate) for category, rate in self.tax_rates.items()
        }

        coupons = {}
        for code, coupon in self.coupons.items():
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

        orders = {}
        for order_id, order in self.orders.items():
            orders[order_id] = {
                "id": order["id"],
                "customer": order["customer"],
                "status": order["status"],
                "items": [dict(item) for item in order["items"]],
                "coupon": order["coupon"],
                "pricing": order["pricing"],
                "paid": None if order["paid"] is None else format_money(order["paid"]),
                "refund": (
                    None if order["refund"] is None else format_money(order["refund"])
                ),
                "cancel_reason": order["cancel_reason"],
                "events": [dict(event) for event in order["events"]],
            }

        return {
            "products": products,
            "stock_levels": self.stock_levels,
            "reorder": self.reorder,
            "stock_logs": self.stock_logs,
            "tiers": tiers,
            "category_discounts": self.category_discounts,
            "tax_rates": tax_rates,
            "coupons": coupons,
            "orders": orders,
            "next_order_num": self.next_order_num,
        }

    def _from_state(self, state):
        self.products = {}
        for sku, data in state.get("products", {}).items():
            self.products[sku] = {
                "sku": data["sku"],
                "name": data["name"],
                "price": Decimal(data["price"]),
                "category": data["category"],
                "active": data["active"],
            }

        self.stock_levels = {
            sku: {"on_hand": data["on_hand"], "reserved": data["reserved"]}
            for sku, data in state.get("stock_levels", {}).items()
        }
        self.reorder = dict(state.get("reorder", {}))
        self.stock_logs = {
            sku: [dict(entry) for entry in entries]
            for sku, entries in state.get("stock_logs", {}).items()
        }
        self.tiers = {
            sku: {int(min_qty): Decimal(price) for min_qty, price in mapping.items()}
            for sku, mapping in state.get("tiers", {}).items()
        }
        self.category_discounts = dict(state.get("category_discounts", {}))
        self.tax_rates = {
            category: Decimal(rate)
            for category, rate in state.get("tax_rates", {}).items()
        }

        self.coupons = {}
        for code, data in state.get("coupons", {}).items():
            if data["kind"] == "fixed":
                value = Decimal(data["value"])
            else:
                value = data["value"]
            self.coupons[code] = {
                "code": data["code"],
                "kind": data["kind"],
                "value": value,
                "min_subtotal": Decimal(data["min_subtotal"]),
                "expires": data["expires"],
                "used_by": data["used_by"],
            }

        self.orders = {}
        for order_id, data in state.get("orders", {}).items():
            self.orders[order_id] = {
                "id": data["id"],
                "customer": data["customer"],
                "status": data["status"],
                "items": [dict(item) for item in data["items"]],
                "coupon": data["coupon"],
                "pricing": data["pricing"],
                "paid": None if data["paid"] is None else Decimal(data["paid"]),
                "refund": None if data["refund"] is None else Decimal(data["refund"]),
                "cancel_reason": data["cancel_reason"],
                "events": [dict(event) for event in data["events"]],
            }

        self.next_order_num = state.get("next_order_num", 1)
