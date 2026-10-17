"""业务异常定义。"""


class ShopError(Exception):
    """所有业务异常的基类。"""


class ValidationError(ShopError):
    """参数类型或取值不合法。"""


class NotFoundError(ShopError):
    """商品、订单等对象不存在。"""


class StockError(ShopError):
    """可用库存不足，或调整后在手数量小于已预留数量。"""


class StateError(ShopError):
    """订单当前状态不允许这个操作。"""


class CouponError(ShopError):
    """优惠券不可用。"""
