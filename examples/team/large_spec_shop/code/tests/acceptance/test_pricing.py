"""定价验收测试（S7-S10）：规则设置、计算规则、报价，以及报价中的优惠券可用性检查。"""

from datetime import datetime
from decimal import Decimal

import pytest

from shopkit import CouponError, NotFoundError, Shop, ValidationError
from shopkit.money import format_money, round_money


class FixedClock:
    """可固定的 clock，便于测试优惠券过期。"""

    def __init__(self, moment):
        self.moment = moment

    def __call__(self):
        return self.moment


@pytest.fixture
def shop():
    s = Shop(clock=FixedClock(datetime(2026, 1, 15, 12, 0, 0)))
    s.add_product("A-1", "Apple", "10.00", "food")
    s.add_product("B-1", "Bread", "20.00", "food")
    s.add_product("C-1", "Cloth", "5.00", "home")
    return s


# ---------------------------------------------------------------------------
# 5.1 规则设置
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("min_qty", [True, False, "10", 1, 0, -1, 2.0])
def test_set_tier_price_validates_min_qty(shop, min_qty):
    with pytest.raises(ValidationError):
        shop.set_tier_price("A-1", min_qty, "8.00")


@pytest.mark.parametrize("price", ["0", "-1", "1.234", 1.5, True])
def test_set_tier_price_validates_unit_price(shop, price):
    with pytest.raises(ValidationError):
        shop.set_tier_price("A-1", 3, price)


def test_set_tier_price_unknown_sku_not_found(shop):
    with pytest.raises(NotFoundError):
        shop.set_tier_price("Z-9", 3, "8.00")


def test_set_tier_price_overwrites_same_min_qty(shop):
    shop.set_tier_price("A-1", 3, "9.00")
    shop.set_tier_price("A-1", 3, "7.00")
    line = shop.quote([{"sku": "A-1", "qty": 3}])["lines"][0]
    assert line["unit_price"] == "7.00"


def test_clear_tier_prices_removes_all(shop):
    shop.set_tier_price("A-1", 3, "9.00")
    shop.set_tier_price("A-1", 5, "8.00")
    shop.clear_tier_prices("A-1")
    line = shop.quote([{"sku": "A-1", "qty": 5}])["lines"][0]
    assert line["unit_price"] == "10.00"


def test_clear_tier_prices_unknown_sku_not_found(shop):
    with pytest.raises(NotFoundError):
        shop.clear_tier_prices("Z-9")


@pytest.mark.parametrize("percent", [-1, 91, 100, True, 10.0, "10"])
def test_set_category_discount_validates_percent(shop, percent):
    with pytest.raises(ValidationError):
        shop.set_category_discount("food", percent)


def test_set_category_discount_zero_clears_and_normalizes(shop):
    shop.set_category_discount("  Food  ", 10)
    line = shop.quote([{"sku": "A-1", "qty": 3}])["lines"][0]  # line_total 30.00
    assert line["discount"] == format_money(
        round_money(Decimal("30.00") * Decimal(10) / Decimal(100))
    )
    shop.set_category_discount("food", 0)  # 0 表示取消
    line = shop.quote([{"sku": "A-1", "qty": 3}])["lines"][0]
    assert line["discount"] == "0.00"


@pytest.mark.parametrize("rate", ["31", "30.01", "1.234", "-1", 1.5, True])
def test_set_tax_rate_validates_range(shop, rate):
    with pytest.raises(ValidationError):
        shop.set_tax_rate("food", rate)


def test_set_tax_rate_applies_and_defaults_to_zero(shop):
    # 未设置过的类别税率为 0
    assert shop.quote([{"sku": "A-1", "qty": 3}])["lines"][0]["tax"] == "0.00"
    shop.set_tax_rate("food", "13")
    line = shop.quote([{"sku": "A-1", "qty": 3}])["lines"][0]  # net 30.00
    assert line["tax"] == format_money(
        round_money(Decimal("30.00") * Decimal("13") / Decimal(100))
    )


# ---------------------------------------------------------------------------
# 5.3 报价：输入校验与结构
# ---------------------------------------------------------------------------

def test_quote_basic_lines_and_totals(shop):
    result = shop.quote([{"sku": "A-1", "qty": 3}])
    assert result == {
        "lines": [
            {
                "sku": "A-1",
                "category": "food",
                "qty": 3,
                "unit_price": "10.00",
                "line_total": "30.00",
                "discount": "0.00",
                "net": "30.00",
                "coupon_share": "0.00",
                "tax": "0.00",
            }
        ],
        "subtotal": format_money(Decimal("30.00")),
        "coupon": None,
        "coupon_discount": format_money(Decimal("0.00")),
        "tax": format_money(Decimal("0.00")),
        "total": format_money(Decimal("30.00")),
    }


@pytest.mark.parametrize("items", [[], None, "A-1", {"sku": "A-1", "qty": 1}, 42])
def test_quote_items_must_be_non_empty_list(shop, items):
    with pytest.raises(ValidationError):
        shop.quote(items)


@pytest.mark.parametrize(
    "item",
    [
        {"sku": "A-1"},  # 缺 qty
        {"qty": 1},  # 缺 sku
        {"sku": "A-1", "qty": 1, "extra": 2},  # 多余的键
        {"sku": 1, "qty": 1},  # sku 不是 str
        {"sku": "A-1", "qty": True},  # qty 不能是 bool
        {"sku": "A-1", "qty": 0},  # qty >= 1
        {"sku": "A-1", "qty": 2.0},  # qty 必须是 int
        "A-1",  # 不是 dict
        ("A-1", 1),  # 不是 dict
    ],
)
def test_quote_item_shape_validation(shop, item):
    with pytest.raises(ValidationError):
        shop.quote([item])


def test_quote_merges_duplicate_sku_keeping_first_position(shop):
    result = shop.quote(
        [
            {"sku": "B-1", "qty": 1},
            {"sku": "A-1", "qty": 2},
            {"sku": "B-1", "qty": 3},
        ]
    )
    assert [line["sku"] for line in result["lines"]] == ["B-1", "A-1"]
    assert result["lines"][0]["qty"] == 4
    assert result["lines"][1]["qty"] == 2


def test_quote_unknown_sku_not_found(shop):
    with pytest.raises(NotFoundError):
        shop.quote([{"sku": "Z-9", "qty": 1}])


def test_quote_inactive_product_validation_error(shop):
    shop.set_active("A-1", False)
    with pytest.raises(ValidationError):
        shop.quote([{"sku": "A-1", "qty": 1}])


# ---------------------------------------------------------------------------
# 5.2 计算规则
# ---------------------------------------------------------------------------

def test_quote_uses_largest_matching_tier(shop):
    shop.set_tier_price("A-1", 3, "9.00")
    shop.set_tier_price("A-1", 5, "8.00")
    assert shop.quote([{"sku": "A-1", "qty": 2}])["lines"][0]["unit_price"] == "10.00"
    assert shop.quote([{"sku": "A-1", "qty": 4}])["lines"][0]["unit_price"] == "9.00"
    assert shop.quote([{"sku": "A-1", "qty": 5}])["lines"][0]["unit_price"] == "8.00"
    assert shop.quote([{"sku": "A-1", "qty": 10}])["lines"][0]["unit_price"] == "8.00"


def test_quote_category_discount_applied(shop):
    shop.set_category_discount("home", 10)
    line = shop.quote([{"sku": "C-1", "qty": 3}])["lines"][0]  # line_total 15.00
    discount = round_money(Decimal("15.00") * Decimal(10) / Decimal(100))
    assert line["line_total"] == format_money(Decimal("15.00"))
    assert line["discount"] == format_money(discount)
    assert line["net"] == format_money(Decimal("15.00") - discount)


def test_quote_spec_example_with_percent_coupon_and_tax(shop):
    # 复现 spec 5.3 的示例：类别折扣 10%，税率 9%，percent 券 10%
    shop.set_category_discount("food", 10)
    shop.set_tax_rate("food", 9)
    shop.add_coupon("SAVE10", "percent", 10)
    result = shop.quote([{"sku": "A-1", "qty": 3}], coupon="SAVE10")
    assert result["lines"] == [
        {
            "sku": "A-1",
            "category": "food",
            "qty": 3,
            "unit_price": "10.00",
            "line_total": "30.00",
            "discount": "3.00",
            "net": "27.00",
            "coupon_share": "2.70",
            "tax": "2.19",
        }
    ]
    assert result["subtotal"] == "27.00"
    assert result["coupon"] == "SAVE10"
    assert result["coupon_discount"] == "2.70"
    assert result["tax"] == "2.19"
    assert result["total"] == "26.49"


def test_quote_coupon_share_remainder_on_last_line(shop):
    shop.add_product("D-1", "Dot", "1.00", "misc")
    shop.add_product("E-1", "Eps", "1.00", "misc")
    shop.add_product("F-1", "Fox", "1.00", "misc")
    shop.add_coupon("SAVE1", "fixed", "1.00")
    result = shop.quote(
        [
            {"sku": "D-1", "qty": 1},
            {"sku": "E-1", "qty": 1},
            {"sku": "F-1", "qty": 1},
        ],
        coupon="SAVE1",
    )
    shares = [line["coupon_share"] for line in result["lines"]]
    assert shares == ["0.33", "0.33", "0.34"]  # 最后一行补差
    assert result["coupon_discount"] == "1.00"
    assert sum(Decimal(share) for share in shares) == Decimal("1.00")


def test_quote_fixed_coupon_capped_and_no_side_effects(shop):
    shop.add_coupon("BIGSAVE", "fixed", "100")
    result = shop.quote([{"sku": "A-1", "qty": 3}], coupon="BIGSAVE")
    assert result["coupon_discount"] == "30.00"  # min(value, subtotal)
    assert result["lines"][0]["coupon_share"] == "30.00"
    assert result["total"] == "0.00"
    # 报价不占用优惠券，也不预留库存
    assert shop._coupons["BIGSAVE"]["used_by"] is None
    assert shop._stock["A-1"]["reserved"] == 0


def test_quote_tax_summed_across_categories(shop):
    shop.set_tax_rate("food", 10)
    shop.set_tax_rate("home", 20)
    result = shop.quote([{"sku": "A-1", "qty": 1}, {"sku": "C-1", "qty": 1}])
    tax_food = round_money(Decimal("10.00") * Decimal(10) / Decimal(100))
    tax_home = round_money(Decimal("5.00") * Decimal(20) / Decimal(100))
    assert result["lines"][0]["tax"] == format_money(tax_food)
    assert result["lines"][1]["tax"] == format_money(tax_home)
    assert result["tax"] == format_money(tax_food + tax_home)
    assert result["total"] == format_money(Decimal("15.00") + tax_food + tax_home)


# ---------------------------------------------------------------------------
# 报价中的优惠券可用性检查（S11）
# ---------------------------------------------------------------------------

def test_quote_coupon_code_normalized(shop):
    shop.add_coupon("SAVE5", "fixed", "1")
    result = shop.quote([{"sku": "A-1", "qty": 1}], coupon="  save5 ")
    assert result["coupon"] == "SAVE5"


def test_quote_coupon_not_found_raises(shop):
    with pytest.raises(CouponError):
        shop.quote([{"sku": "A-1", "qty": 1}], coupon="NOPE1")


def test_quote_coupon_used_raises(shop):
    shop.add_coupon("USED1", "fixed", "1")
    shop._coupons["USED1"]["used_by"] = "O0001"
    with pytest.raises(CouponError):
        shop.quote([{"sku": "A-1", "qty": 1}], coupon="USED1")


def test_quote_coupon_expired_raises(shop):
    shop.add_coupon("OLD1", "fixed", "1", expires="2026-01-14")
    with pytest.raises(CouponError):
        shop.quote([{"sku": "A-1", "qty": 1}], coupon="OLD1")


def test_quote_coupon_below_min_subtotal_raises(shop):
    shop.add_coupon("BIG1", "fixed", "1", min_subtotal="100")
    with pytest.raises(CouponError):
        shop.quote([{"sku": "A-1", "qty": 1}], coupon="BIG1")


def test_quote_coupon_expires_today_is_usable(shop):
    shop.add_coupon("TODAY1", "fixed", "1", expires="2026-01-15")
    result = shop.quote([{"sku": "A-1", "qty": 1}], coupon="TODAY1")
    assert result["coupon"] == "TODAY1"


@pytest.mark.parametrize("coupon", [123, ["SAVE5"], 4.5])
def test_quote_coupon_non_str_validation_error(shop, coupon):
    with pytest.raises(ValidationError):
        shop.quote([{"sku": "A-1", "qty": 1}], coupon=coupon)
