def daily_summary(orders):
    print(f"[LOG] building summary for {len(orders)} orders")
    if not orders:
        print("[LOG][WARN] no orders today")
    total = sum(o["total"] for o in orders)
    return f"今日订单 {len(orders)} 笔，合计 {total:.2f}"
