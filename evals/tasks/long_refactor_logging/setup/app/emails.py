def send_receipt(user, order):
    print(f"[LOG] sending receipt to {user['name']}")
    if not order["items"]:
        print("[LOG][WARN] receipt for empty order")
    return f"Receipt: {order['total']:.2f}"
