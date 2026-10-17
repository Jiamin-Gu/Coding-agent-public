"""shopkit 的门面类。"""

from datetime import datetime

from .catalog import CatalogMixin
from .coupons import CouponMixin
from .inventory import InventoryMixin
from .orders import OrderMixin
from .pricing import PricingMixin
from .reports import ReportMixin
from .storage import StorageMixin


class Shop(
    CatalogMixin,
    InventoryMixin,
    PricingMixin,
    CouponMixin,
    OrderMixin,
    ReportMixin,
    StorageMixin,
):
    """一个小型网店后台的核心逻辑。"""

    def __init__(self, clock=None):
        self._clock = clock if clock is not None else datetime.now

        # 商品目录
        self.products = {}
        # 库存
        self.stock_levels = {}
        self.reorder = {}
        self.stock_logs = {}
        # 定价规则
        self.tiers = {}
        self.category_discounts = {}
        self.tax_rates = {}
        # 优惠券
        self.coupons = {}
        # 订单
        self.orders = {}
        self.next_order_num = 1

    def _event_time(self):
        return self._clock().isoformat(timespec="seconds")
