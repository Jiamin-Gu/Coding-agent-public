import json

import pytest

from shopkit import Shop, errors


@pytest.fixture
def busy(stocked, clock):
    """四个订单：两个在 3 月上旬发货，一个付了款没发货，一个 3 月 10 日发货。"""
    s = stocked
    s.set_category_discount("food", 10)
    s.set_tax_rate("food", "9")
    s.set_tax_rate("book", "13")
    s.add_coupon("SAVE10", "percent", 10)

    o1 = s.create_order("张三", [{"sku": "APPLE", "qty": 3}, {"sku": "MILK", "qty": 2}, {"sku": "BOOK-1", "qty": 1}],
                        coupon="SAVE10")
    s.place_order(o1)
    s.pay(o1, "91.38")
    clock.set("2026-03-02T15:00:00")
    s.ship(o1)

    o2 = s.create_order("李四", [{"sku": "APPLE", "qty": 10}])
    s.place_order(o2)  # 31.50 + 税 2.835→2.84 = 34.34
    s.pay(o2, "34.34")
    clock.set("2026-03-05T23:59:59")
    s.ship(o2)
    clock.set("2026-03-06T10:00:00")
    s.deliver(o2)

    o3 = s.create_order("王五", [{"sku": "MILK", "qty": 1}])
    s.place_order(o3)  # 10.80 + 税 0.972→0.97 = 11.77
    s.pay(o3, "11.77")

    o4 = s.create_order("赵六", [{"sku": "BOOK-1", "qty": 2}])
    s.place_order(o4)  # 119.80 + 税 15.574→15.57 = 135.37
    s.pay(o4, "135.37")
    clock.set("2026-03-10T09:00:00")
    s.ship(o4)
    return s


def test_sales_report_range(busy):
    assert busy.sales_report("2026-03-01", "2026-03-05") == {
        "orders": 2, "units": 16, "subtotal": "122.45", "coupon_discount": "9.10", "tax": "12.37",
        "revenue": "125.72",
        "by_category": [{"category": "food", "units": 15, "net": "62.55"},
                        {"category": "book", "units": 1, "net": "59.90"}]}


def test_sales_report_whole_month(busy):
    r = busy.sales_report("2026-03-01", "2026-03-31")
    assert (r["orders"], r["units"], r["subtotal"], r["coupon_discount"], r["tax"], r["revenue"]) == (
        3, 18, "242.25", "9.10", "27.94", "261.09")
    assert r["by_category"] == [{"category": "book", "units": 3, "net": "179.70"},
                                {"category": "food", "units": 15, "net": "62.55"}]


def test_sales_report_single_day_and_empty(busy):
    assert busy.sales_report("2026-03-05", "2026-03-05")["orders"] == 1  # 当天 23:59:59 发货也算
    assert busy.sales_report("2026-04-01", "2026-04-30") == {
        "orders": 0, "units": 0, "subtotal": "0.00", "coupon_discount": "0.00", "tax": "0.00", "revenue": "0.00",
        "by_category": []}


@pytest.mark.parametrize("start,end", [("2026-03-06", "2026-03-01"), ("2026-3-1", "2026-03-31"),
                                       ("2026-03-01", "2026-02-30"), ("2026/03/01", "2026-03-31"), (None, "2026-03-31")])
def test_sales_report_invalid(busy, start, end):
    with pytest.raises(errors.ValidationError):
        busy.sales_report(start, end)


def test_top_products(busy):
    assert busy.top_products() == [{"sku": "APPLE", "units": 13}, {"sku": "BOOK-1", "units": 3},
                                   {"sku": "MILK", "units": 2}]
    assert busy.top_products(limit=2) == [{"sku": "APPLE", "units": 13}, {"sku": "BOOK-1", "units": 3}]
    assert busy.top_products(start="2026-03-06") == [{"sku": "BOOK-1", "units": 2}]
    assert busy.top_products(end="2026-03-02") == [{"sku": "APPLE", "units": 3}, {"sku": "MILK", "units": 2},
                                                   {"sku": "BOOK-1", "units": 1}]
    for bad in (0, -1, True, "3"):
        with pytest.raises(errors.ValidationError):
            busy.top_products(limit=bad)
    with pytest.raises(errors.ValidationError):
        busy.top_products(start="2026-03-32")


def test_top_products_ties_sorted_by_sku(stocked):
    for sku in ("MILK", "APPLE"):
        oid = stocked.create_order("张三", [{"sku": sku, "qty": 2}])
        total = stocked.place_order(oid)["pricing"]["total"]
        stocked.pay(oid, total)
        stocked.ship(oid)
    assert stocked.top_products() == [{"sku": "APPLE", "units": 2}, {"sku": "MILK", "units": 2}]


def test_inventory_value(busy):
    # APPLE 87 × 3.50 + MILK 18 × 12（王五的订单只预留、没发货）+ BOOK-1 2 × 59.90
    assert busy.inventory_value() == "640.30"
    busy.set_active("BOOK-1", False)
    assert busy.inventory_value() == "640.30"
    assert Shop().inventory_value() == "0.00"


def test_save_and_load_roundtrip(busy, clock, tmp_path):
    busy.set_tier_price("APPLE", 10, "3.00")
    busy.set_reorder_level("MILK", 20)
    busy.adjust("APPLE", -2, "损耗")
    draft = busy.create_order("钱七", [{"sku": "APPLE", "qty": 1}])
    path = tmp_path / "shop.json"
    busy.save(path)
    assert json.loads(path.read_text(encoding="utf-8"))  # 合法的 UTF-8 JSON
    assert [p.name for p in tmp_path.iterdir()] == ["shop.json"]  # 没有留下临时文件

    loaded = Shop.load(path, clock=clock)
    assert loaded.list_products() == busy.list_products()
    assert loaded.list_orders() == busy.list_orders()
    for sku in ("APPLE", "MILK", "BOOK-1"):
        assert loaded.stock(sku) == busy.stock(sku)
        assert loaded.stock_log(sku) == busy.stock_log(sku)
    assert loaded.low_stock() == busy.low_stock()
    assert loaded.get_coupon("SAVE10") == busy.get_coupon("SAVE10")
    assert loaded.get_coupon("SAVE10")["used_by"] == "O0001"
    assert loaded.sales_report("2026-03-01", "2026-03-31") == busy.sales_report("2026-03-01", "2026-03-31")
    assert loaded.inventory_value() == busy.inventory_value()
    items = [{"sku": "APPLE", "qty": 12}, {"sku": "MILK", "qty": 1}, {"sku": "BOOK-1", "qty": 1}]
    assert loaded.quote(items) == busy.quote(items)  # 阶梯价、折扣、税率都恢复了

    # 恢复后继续工作：订单号接着编，预留和优惠券占用也都还在
    assert loaded.create_order("孙八") == "O0006"
    loaded.add_item(draft, "MILK", 1)
    loaded.place_order(draft)
    assert loaded.stock("MILK")["reserved"] == 2
    with pytest.raises(errors.CouponError):
        loaded.quote([{"sku": "MILK", "qty": 1}], coupon="SAVE10")
    loaded.cancel("O0003", "不要了")
    assert loaded.get_order("O0003")["refund"] == "11.77"
    assert loaded.stock("MILK")["reserved"] == 1


def test_save_overwrites_and_load_missing(stocked, tmp_path):
    path = tmp_path / "shop.json"
    stocked.save(path)
    stocked.add_product("NEW", "新品", "1", "misc")
    stocked.save(path)
    assert [p["sku"] for p in Shop.load(path).list_products()] == ["APPLE", "BOOK-1", "MILK", "NEW"]
    with pytest.raises(errors.NotFoundError):
        Shop.load(tmp_path / "missing.json")
