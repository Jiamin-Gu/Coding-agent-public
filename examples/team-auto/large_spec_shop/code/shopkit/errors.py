"""Business exception hierarchy for shopkit."""


class ShopError(Exception):
    """Base class for all shopkit business errors."""


class ValidationError(ShopError):
    """An argument has an invalid type or value."""


class NotFoundError(ShopError):
    """A requested product, order or archive file does not exist."""


class StockError(ShopError):
    """Available stock is insufficient or on_hand would drop below reserved."""


class StateError(ShopError):
    """The order is not in a state that allows the requested operation."""


class CouponError(ShopError):
    """A coupon is unavailable (missing, used, expired or below minimum)."""
