import logging
import re
from pathlib import Path

import pytest

from app import config, db, emails, main, orders, payments, reports, users
from app.log import get_logger


@pytest.fixture
def logs(caplog):
    caplog.set_level(logging.INFO, logger="app")
    return lambda: [(r.name, r.levelname, r.getMessage()) for r in caplog.records]


def out_lines(capsys):
    return capsys.readouterr().out.splitlines()


def test_get_logger():
    assert get_logger("db").name == "app.db" and get_logger("x") is logging.getLogger("app.x")
    assert not logging.getLogger("app").handlers and not logging.getLogger("app.db").handlers


def test_no_log_prints_left():
    for f in Path("app").glob("*.py"):
        assert not re.search(r'print\(\s*f?["\']\[LOG\]', f.read_text(encoding="utf-8")), f


def test_config(logs, capsys):
    assert config.load_config("x.yaml") == {"path": "x.yaml", "debug": False}
    assert logs() == [("app.config", "INFO", "loading config from x.yaml"),
                      ("app.config", "WARNING", "unusual config extension: x.yaml")]
    assert out_lines(capsys) == []


def test_db(logs, capsys):
    assert db.connect("mysql://h") == {"url": "mysql://h", "connected": False}
    assert logs() == [("app.db", "INFO", "connecting to mysql://h"), ("app.db", "ERROR", "unsupported database: mysql://h")]
    assert out_lines(capsys) == []


def test_users(logs, capsys):
    assert users.create_user({"connected": False}, "bob") == {"name": "bob"}
    assert users.create_user({"connected": True}, "") is None
    assert logs() == [("app.users", "INFO", "creating user bob"),
                      ("app.users", "WARNING", "database offline, user kept in memory"),
                      ("app.users", "INFO", "creating user "), ("app.users", "ERROR", "empty user name")]
    assert out_lines(capsys) == ["已创建用户：bob"]


def test_orders_and_payments(logs, capsys):
    order = orders.create_order({"name": "amy"}, [("tv", 1, 1500.0)])
    assert payments.charge(order, "cash") == {"status": "failed"}
    assert payments.charge({"total": 0}, "wallet") == {"status": "paid"}
    assert logs() == [("app.orders", "INFO", "creating order for amy with 1 items"),
                      ("app.orders", "WARNING", "large order: 1500.00"),
                      ("app.payments", "INFO", "charging 1500.00 via cash"),
                      ("app.payments", "ERROR", "unknown payment method: cash"),
                      ("app.payments", "INFO", "charging 0.00 via wallet"),
                      ("app.payments", "WARNING", "zero amount order")]
    assert out_lines(capsys) == ["订单金额：1500.00", "支付成功"]


def test_emails_and_reports(logs, capsys):
    assert emails.send_receipt({"name": "amy"}, {"items": [], "total": 0}) == "Receipt: 0.00"
    assert reports.daily_summary([]) == "今日订单 0 笔，合计 0.00"
    assert logs() == [("app.emails", "INFO", "sending receipt to amy"), ("app.emails", "WARNING", "receipt for empty order"),
                      ("app.reports", "INFO", "building summary for 0 orders"), ("app.reports", "WARNING", "no orders today")]
    assert out_lines(capsys) == []


def test_main_run(logs, capsys):
    assert main.run() == "paid"
    assert out_lines(capsys) == ["提示：调试信息以 [LOG] 开头的旧格式已经废弃", "已创建用户：alice", "订单金额：60.00",
                                 "支付成功", "今日订单 1 笔，合计 60.00"]
    assert [m for m in logs() if m[0] == "app.main"] == [("app.main", "INFO", "starting with method card"),
                                                         ("app.main", "INFO", "done")]
    assert len(logs()) == 9
