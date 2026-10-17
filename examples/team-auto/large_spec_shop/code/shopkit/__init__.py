"""shopkit: a small shop back office core (catalogue, stock, orders, reports).

Public entry point is :class:`shopkit.Shop`.
"""

from . import money
from .errors import (
    CouponError,
    NotFoundError,
    ShopError,
    StateError,
    StockError,
    ValidationError,
)
from .money import format_money, parse_money, round_money
from .shop import Shop

__all__ = [
    "Shop",
    "ShopError",
    "ValidationError",
    "NotFoundError",
    "StockError",
    "StateError",
    "CouponError",
    "money",
    "parse_money",
    "round_money",
    "format_money",
]
