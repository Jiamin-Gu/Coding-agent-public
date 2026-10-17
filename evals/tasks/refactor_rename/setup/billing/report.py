from .core import calc_total


def summary(orders):
    """orders: {订单号: [(单价, 数量), ...]}，返回每个订单的总价。"""
    return {order_id: calc_total(items) for order_id, items in orders.items()}
