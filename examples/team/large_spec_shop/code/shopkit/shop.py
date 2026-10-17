"""shopkit 的对外入口：``Shop`` 类。

``Shop`` 由各特性模块的 mixin 组合而成，只负责初始化共享状态和提供时间助手。
"""

from datetime import datetime

from shopkit.catalog import CatalogMixin
from shopkit.coupons import CouponMixin
from shopkit.inventory import InventoryMixin
from shopkit.orders import OrderMixin
from shopkit.pricing import PricingMixin
from shopkit.reports import ReportMixin
from shopkit.storage import StorageMixin


class Shop(
    CatalogMixin,
    InventoryMixin,
    PricingMixin,
    CouponMixin,
    OrderMixin,
    ReportMixin,
    StorageMixin,
):
    """网店后台核心逻辑的单一入口。"""

    def __init__(self, clock=None):
        # clock 是无参函数，返回不带时区的 datetime；不传时用 datetime.now
        self._clock = clock if clock is not None else datetime.now

        # 商品目录：sku -> product dict
        self._products = {}
        # 库存：sku -> {"on_hand", "reserved", "reorder_level", "log"}
        self._stock = {}
        # 阶梯价：sku -> {min_qty(int): unit_price(Decimal)}
        self._tiers = {}
        # 类别折扣：category(小写) -> percent(int)，0 表示没有
        self._discounts = {}
        # 类别税率：category(小写) -> rate(Decimal 百分比)
        self._tax_rates = {}
        # 优惠券：code -> coupon dict
        self._coupons = {}
        # 订单：order_id -> order dict
        self._orders = {}
        # 下一个订单号（从 1 开始）
        self._next_no = 1

    def _now(self) -> str:
        """当前事件时间，格式 ``clock().isoformat(timespec="seconds")``。"""
        return self._clock().isoformat(timespec="seconds")