from .log import get_logger

logger = get_logger("reports")


def daily_summary(orders):
    logger.info(f"building summary for {len(orders)} orders")
    if not orders:
        logger.warning("no orders today")
    total = sum(o["total"] for o in orders)
    return f"今日订单 {len(orders)} 笔，合计 {total:.2f}"
