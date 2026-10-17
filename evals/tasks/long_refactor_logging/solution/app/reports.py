from .log import get_logger

log = get_logger("reports")


def daily_summary(orders):
    log.info(f"building summary for {len(orders)} orders")
    if not orders:
        log.warning("no orders today")
    total = sum(o["total"] for o in orders)
    return f"今日订单 {len(orders)} 笔，合计 {total:.2f}"
