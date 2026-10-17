from .log import get_logger

logger = get_logger("payments")


def charge(order, method):
    logger.info(f"charging {order['total']:.2f} via {method}")
    if method not in ("card", "wallet"):
        logger.error(f"unknown payment method: {method}")
        return {"status": "failed"}
    if order["total"] == 0:
        logger.warning("zero amount order")
    print("支付成功")
    return {"status": "paid"}
