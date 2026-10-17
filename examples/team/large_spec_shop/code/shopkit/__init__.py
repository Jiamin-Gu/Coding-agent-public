"""shopkit —— 小型网店后台的核心逻辑库。

对外入口：``from shopkit import Shop``。
所有异常类可以从 ``shopkit`` 或 ``shopkit.errors`` 导入；
金额工具函数在 ``shopkit.money``。
"""

from shopkit.errors import (
    CouponError,
    NotFoundError,
    ShopError,
    StateError,
    StockError,
    ValidationError,
)
from shopkit.money import format_money, parse_money, round_money
from shopkit.shop import Shop

__all__ = [
    "Shop",
    "ShopError",
    "ValidationError",
    "NotFoundError",
    "StockError",
    "StateError",
    "CouponError",
    "parse_money",
    "round_money",
    "format_money",
]