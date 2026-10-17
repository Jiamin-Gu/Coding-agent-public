from .core import compute_total


def summary(orders):
    return {order_id: compute_total(items) for order_id, items in orders.items()}
