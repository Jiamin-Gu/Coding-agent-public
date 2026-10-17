from .log import get_logger

log = get_logger("payments")


def charge(order, method):
    log.info(f"charging {order['total']:.2f} via {method}")
    if method not in ("card", "wallet"):
        log.error(f"unknown payment method: {method}")
        return {"status": "failed"}
    if order["total"] == 0:
        log.warning("zero amount order")
    print("支付成功")
    return {"status": "paid"}
