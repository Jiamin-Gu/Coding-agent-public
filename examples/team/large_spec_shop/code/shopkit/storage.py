"""持久化：``StorageMixin`` 的 ``save`` / ``load``（UTF-8 JSON，原子写入）。"""

import copy
import json
import os
import tempfile
from decimal import Decimal

from shopkit.errors import NotFoundError
from shopkit.money import format_money

_VERSION = 1


class StorageMixin:
    """把整个商店状态序列化为 JSON 存档，并从存档恢复，供 :class:`~shopkit.shop.Shop` 混入。"""

    # --- 公开接口 -------------------------------------------------------

    def save(self, path):
        """把全部状态写成 UTF-8 JSON；先写同目录临时文件再原子替换目标文件。"""
        data = self._serialize()

        directory = os.path.dirname(os.path.abspath(path))
        fd, tmp_path = tempfile.mkstemp(
            dir=directory, prefix=".shopkit-", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False)
            os.replace(tmp_path, path)
        except Exception:
            # 失败时清理临时文件，绝不破坏原文件
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            raise

    @classmethod
    def load(cls, path, clock=None):
        """从 ``save`` 写出的文件恢复一个 ``Shop``；文件不存在 → NotFoundError。"""
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except FileNotFoundError:
            raise NotFoundError(f"存档文件不存在：{path!r}") from None

        shop = cls(clock=clock)

        shop._products = {
            sku: {
                "sku": product["sku"],
                "name": product["name"],
                "price": Decimal(str(product["price"])),
                "category": product["category"],
                "active": product["active"],
            }
            for sku, product in data.get("products", {}).items()
        }

        shop._stock = {
            sku: {
                "on_hand": int(entry["on_hand"]),
                "reserved": int(entry["reserved"]),
                "reorder_level": int(entry["reorder_level"]),
                "log": [dict(item) for item in entry["log"]],
            }
            for sku, entry in data.get("stock", {}).items()
        }

        shop._tiers = {
            sku: {int(min_qty): Decimal(str(price)) for min_qty, price in tiers.items()}
            for sku, tiers in data.get("tiers", {}).items()
        }

        shop._discounts = {
            category: int(percent)
            for category, percent in data.get("discounts", {}).items()
        }

        shop._tax_rates = {
            category: Decimal(str(rate))
            for category, rate in data.get("tax_rates", {}).items()
        }

        shop._coupons = {}
        for code, coupon in data.get("coupons", {}).items():
            if coupon["kind"] == "fixed":
                value = Decimal(str(coupon["value"]))
            else:
                value = int(coupon["value"])
            shop._coupons[code] = {
                "code": coupon["code"],
                "kind": coupon["kind"],
                "value": value,
                "min_subtotal": Decimal(str(coupon["min_subtotal"])),
                "expires": coupon["expires"],
                "used_by": coupon["used_by"],
            }

        shop._orders = copy.deepcopy(data.get("orders", {}))

        shop._next_no = int(data.get("next_no", 1))

        return shop

    # --- 内部：序列化 ---------------------------------------------------

    def _serialize(self) -> dict:
        """把内部状态转成可 JSON 序列化的结构。"""
        products = {
            sku: {
                "sku": product["sku"],
                "name": product["name"],
                "price": format_money(product["price"]),
                "category": product["category"],
                "active": product["active"],
            }
            for sku, product in self._products.items()
        }

        stock = {
            sku: {
                "on_hand": entry["on_hand"],
                "reserved": entry["reserved"],
                "reorder_level": entry["reorder_level"],
                "log": [dict(item) for item in entry["log"]],
            }
            for sku, entry in self._stock.items()
        }

        tiers = {
            sku: {str(min_qty): format_money(price) for min_qty, price in prices.items()}
            for sku, prices in self._tiers.items()
        }

        discounts = {category: percent for category, percent in self._discounts.items()}

        tax_rates = {
            category: format_money(rate) for category, rate in self._tax_rates.items()
        }

        coupons = {}
        for code, coupon in self._coupons.items():
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

        return {
            "version": _VERSION,
            "products": products,
            "stock": stock,
            "tiers": tiers,
            "discounts": discounts,
            "tax_rates": tax_rates,
            "coupons": coupons,
            "orders": copy.deepcopy(self._orders),
            "next_no": self._next_no,
        }
