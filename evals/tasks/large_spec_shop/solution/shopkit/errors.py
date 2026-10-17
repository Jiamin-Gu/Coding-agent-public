class ShopError(Exception):
    pass


class ValidationError(ShopError):
    pass


class NotFoundError(ShopError):
    pass


class StockError(ShopError):
    pass


class StateError(ShopError):
    pass


class CouponError(ShopError):
    pass
