"""商品目录：add_product / get_product / update_price / set_active / list_products。

内部商品 dict 的 price 保存为 ``Decimal``（两位小数），对外返回时格式化成字符串。
"""

import re

from shopkit.errors import NotFoundError, ValidationError
from shopkit.money import format_money, parse_money

_SKU_RE = re.compile(r"[A-Z0-9-]{1,20}")


class CatalogMixin:
    """商品目录相关方法，供 :class:`~shopkit.shop.Shop` 混入。"""

    # --- 辅助 -----------------------------------------------------------

    def _normalize_category(self, value) -> str:
        """类别规范化：strip + 转小写；非 str 或规范化后为空 → ValidationError。"""
        if not isinstance(value, str):
            raise ValidationError(f"类别必须是字符串，不能是 {type(value).__name__}")
        normalized = value.strip().lower()
        if normalized == "":
            raise ValidationError("类别不能为空")
        return normalized

    def _get_product(self, sku) -> dict:
        """返回内部商品 dict（不存在 → NotFoundError）。"""
        if not isinstance(sku, str):
            raise ValidationError(f"sku 必须是字符串，不能是 {type(sku).__name__}")
        try:
            return self._products[sku]
        except KeyError:
            raise NotFoundError(f"商品不存在：{sku!r}") from None

    @staticmethod
    def _public_product(product) -> dict:
        """把内部商品 dict 转成对外返回格式（price 为字符串）。"""
        return {
            "sku": product["sku"],
            "name": product["name"],
            "price": format_money(product["price"]),
            "category": product["category"],
            "active": product["active"],
        }

    # --- 公开接口 -------------------------------------------------------

    def add_product(self, sku, name, price, category, active=True) -> dict:
        """新增商品，并初始化零库存。sku 重复 → ValidationError。"""
        if not isinstance(sku, str):
            raise ValidationError(f"sku 必须是字符串，不能是 {type(sku).__name__}")
        if _SKU_RE.fullmatch(sku) is None:
            raise ValidationError(f"sku 格式不合法：{sku!r}")

        if not isinstance(name, str):
            raise ValidationError(f"name 必须是字符串，不能是 {type(name).__name__}")
        clean_name = name.strip()
        if clean_name == "":
            raise ValidationError("name 不能为空")

        clean_price = parse_money(price)
        if clean_price <= 0:
            raise ValidationError("price 必须大于 0")

        clean_category = self._normalize_category(category)

        if not isinstance(active, bool):
            raise ValidationError(f"active 必须是 bool，不能是 {type(active).__name__}")

        if sku in self._products:
            raise ValidationError(f"商品已存在：{sku!r}")

        product = {
            "sku": sku,
            "name": clean_name,
            "price": clean_price,
            "category": clean_category,
            "active": active,
        }
        self._products[sku] = product
        self._stock[sku] = {"on_hand": 0, "reserved": 0, "reorder_level": 0, "log": []}
        return self._public_product(product)

    def get_product(self, sku) -> dict:
        """返回商品的对外格式。"""
        return self._public_product(self._get_product(sku))

    def update_price(self, sku, price) -> dict:
        """更新商品价格（先校验 price，再查 sku）。"""
        clean_price = parse_money(price)
        if clean_price <= 0:
            raise ValidationError("price 必须大于 0")
        product = self._get_product(sku)
        product["price"] = clean_price
        return self._public_product(product)

    def set_active(self, sku, active) -> dict:
        """设置商品上架状态（先校验 active，再查 sku）。"""
        if not isinstance(active, bool):
            raise ValidationError(f"active 必须是 bool，不能是 {type(active).__name__}")
        product = self._get_product(sku)
        product["active"] = active
        return self._public_product(product)

    def list_products(self, category=None, active_only=False) -> list:
        """按 sku 升序列出商品，可按规范化类别和上架状态过滤。"""
        normalized = None
        if category is not None:
            normalized = self._normalize_category(category)

        result = []
        for sku in sorted(self._products):
            product = self._products[sku]
            if normalized is not None and product["category"] != normalized:
                continue
            if active_only and not product["active"]:
                continue
            result.append(self._public_product(product))
        return result
