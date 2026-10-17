"""shopkit 异常体系。

所有业务异常都可以从 ``shopkit`` 或 ``shopkit.errors`` 导入。
"""


class ShopError(Exception):
    """所有业务异常的基类。"""


class ValidationError(ShopError):
    """参数类型或取值不合法。"""


class NotFoundError(ShopError):
    """商品、订单不存在；从订单里删除订单中没有的商品；读取不存在的存档文件。"""


class StockError(ShopError):
    """可用库存不足；库存调整后在手数量小于已预留数量。"""


class StateError(ShopError):
    """订单当前状态不允许这个操作。"""


class CouponError(ShopError):
    """优惠券不可用：不存在、已被使用、已过期、未达到最低消费。"""