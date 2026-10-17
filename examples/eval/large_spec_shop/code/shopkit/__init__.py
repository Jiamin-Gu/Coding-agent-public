"""shopkit: 小型网店后台核心逻辑。"""

from .shop import Shop
from .errors import (
    ShopError,
    ValidationError,
    NotFoundError,
    StockError,
    StateError,
    CouponError,
)

__all__ = [
    "Shop",
    "ShopError",
    "ValidationError",
    "NotFoundError",
    "StockError",
    "StateError",
    "CouponError",
]
