"""Product catalog mixin.

The mixin operates on the shared state attributes documented in the project
contract (``self._products``, ``self._stock``, ``self._logs`` and
``self._tiers``), which are created by ``Shop``.
"""

from ._util import norm_category, norm_text, require_bool, validate_sku
from .errors import NotFoundError, ValidationError
from .money import format_money, parse_money


class CatalogMixin:
    """Product catalogue operations (SPEC section 3)."""

    # -- internal helpers -------------------------------------------------

    def _product(self, sku):
        """Return the internal product dict for ``sku`` or raise NotFoundError."""
        try:
            return self._products[sku]
        except (KeyError, TypeError):
            raise NotFoundError(f"product {sku!r} not found")

    @staticmethod
    def _validated_price(price):
        """Parse ``price`` and require it to be strictly positive."""
        amount = parse_money(price)
        if amount <= 0:
            raise ValidationError("price must be > 0")
        return amount

    # -- public API -------------------------------------------------------

    def add_product(self, sku, name, price, category, active=True):
        """Add a new product and initialise its stock, log and tier state."""
        sku = validate_sku(sku)
        name = norm_text(name, "name")
        amount = self._validated_price(price)
        category = norm_category(category)
        active = require_bool(active, "active")

        if sku in self._products:
            raise ValidationError(f"product {sku!r} already exists")

        self._products[sku] = {
            "sku": sku,
            "name": name,
            "price": amount,
            "category": category,
            "active": active,
        }
        self._stock[sku] = {"on_hand": 0, "reserved": 0, "reorder_level": 0}
        self._logs[sku] = []
        self._tiers[sku] = {}
        return self.get_product(sku)

    def get_product(self, sku):
        """Return a public view of the product."""
        product = self._product(sku)
        return {
            "sku": product["sku"],
            "name": product["name"],
            "price": format_money(product["price"]),
            "category": product["category"],
            "active": product["active"],
        }

    def update_price(self, sku, price):
        """Update the current price of an existing product."""
        amount = self._validated_price(price)
        product = self._product(sku)
        product["price"] = amount
        return self.get_product(sku)

    def set_active(self, sku, active):
        """Set whether a product is on sale."""
        active = require_bool(active, "active")
        product = self._product(sku)
        product["active"] = active
        return self.get_product(sku)

    def list_products(self, category=None, active_only=False):
        """List products sorted by sku, optionally filtered."""
        if category is not None:
            category = norm_category(category)
        result = []
        for sku in sorted(self._products):
            product = self._products[sku]
            if category is not None and product["category"] != category:
                continue
            if active_only and not product["active"]:
                continue
            result.append(self.get_product(sku))
        return result
