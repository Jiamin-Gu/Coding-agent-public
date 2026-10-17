from .log import get_logger

log = get_logger("orders")


def create_order(user, items):
    log.info(f"creating order for {user['name']} with {len(items)} items")
    total = sum(qty * price for _, qty, price in items)
    if total > 1000:
        log.warning(f"large order: {total:.2f}")
    print(f"订单金额：{total:.2f}")
    return {"user": user["name"], "items": items, "total": total}
