"""商品目录。"""

from .errors import NotFoundError, ValidationError
from .money import format_money, parse_money
from ._util import normalize_category, normalize_name, validate_sku

_ACTIVE = "active"


class CatalogMixin:
    """商品目录相关方法。"""

    def add_product(self, sku, name, price, category, active=True):
        validate_sku(sku)
        clean_name = normalize_name(name)
        clean_price = parse_money(price)
        if clean_price <= 0:
            raise ValidationError("价格必须大于 0")
        clean_category = normalize_category(category)
        if not isinstance(active, bool):
            raise ValidationError("active 必须是 bool")

        if sku in self.products:
            raise ValidationError("商品已存在: {!r}".format(sku))

        self.products[sku] = {
            "sku": sku,
            "name": clean_name,
            "price": clean_price,
            "category": clean_category,
            "active": active,
        }
        self.stock_levels[sku] = {"on_hand": 0, "reserved": 0}
        self.reorder[sku] = 0
        self.stock_logs[sku] = []
        self.tiers[sku] = {}
        return self.get_product(sku)

    def get_product(self, sku):
        product = self.products.get(sku)
        if product is None:
            raise NotFoundError("商品不存在: {!r}".format(sku))
        return self._product_view(product)

    def update_price(self, sku, price):
        clean_price = parse_money(price)
        if clean_price <= 0:
            raise ValidationError("价格必须大于 0")
        product = self.products.get(sku)
        if product is None:
            raise NotFoundError("商品不存在: {!r}".format(sku))
        product["price"] = clean_price
        return self._product_view(product)

    def set_active(self, sku, active):
        if not isinstance(active, bool):
            raise ValidationError("active 必须是 bool")
        product = self.products.get(sku)
        if product is None:
            raise NotFoundError("商品不存在: {!r}".format(sku))
        product["active"] = active
        return self._product_view(product)

    def list_products(self, category=None, active_only=False):
        if not isinstance(active_only, bool):
            raise ValidationError("active_only 必须是 bool")
        clean_category = None
        if category is not None:
            clean_category = normalize_category(category)

        result = []
        for sku in sorted(self.products):
            product = self.products[sku]
            if clean_category is not None and product["category"] != clean_category:
                continue
            if active_only and not product["active"]:
                continue
            result.append(self._product_view(product))
        return result

    @staticmethod
    def _product_view(product):
        return {
            "sku": product["sku"],
            "name": product["name"],
            "price": format_money(product["price"]),
            "category": product["category"],
            "active": product["active"],
        }
