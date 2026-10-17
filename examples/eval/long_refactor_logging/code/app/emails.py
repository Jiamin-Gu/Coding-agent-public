from .log import get_logger

logger = get_logger("emails")


def send_receipt(user, order):
    logger.info(f"sending receipt to {user['name']}")
    if not order["items"]:
        logger.warning("receipt for empty order")
    return f"Receipt: {order['total']:.2f}"
