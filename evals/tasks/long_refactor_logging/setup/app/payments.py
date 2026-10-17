def charge(order, method):
    print(f"[LOG] charging {order['total']:.2f} via {method}")
    if method not in ("card", "wallet"):
        print(f"[LOG][ERROR] unknown payment method: {method}")
        return {"status": "failed"}
    if order["total"] == 0:
        print("[LOG][WARN] zero amount order")
    print("支付成功")
    return {"status": "paid"}
