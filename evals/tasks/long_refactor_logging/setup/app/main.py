from . import config, db, emails, orders, payments, reports, users


def run(method="card"):
    print("提示：调试信息以 [LOG] 开头的旧格式已经废弃")
    print(f"[LOG] starting with method {method}")
    config.load_config("app.ini")
    conn = db.connect("sqlite:///app.db")
    user = users.create_user(conn, "alice")
    order = orders.create_order(user, [("book", 2, 30.0)])
    result = payments.charge(order, method)
    emails.send_receipt(user, order)
    print(reports.daily_summary([order]))
    print("[LOG] done")
    return result["status"]
