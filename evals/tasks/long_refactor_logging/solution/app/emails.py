from .log import get_logger

log = get_logger("emails")


def send_receipt(user, order):
    log.info(f"sending receipt to {user['name']}")
    if not order["items"]:
        log.warning("receipt for empty order")
    return f"Receipt: {order['total']:.2f}"
