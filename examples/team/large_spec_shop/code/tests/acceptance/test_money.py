"""验收测试：S4 金额工具 parse_money / round_money / format_money。"""

from datetime import datetime
from decimal import Decimal

import pytest

from shopkit.errors import ValidationError
from shopkit.money import format_money, parse_money, round_money


class FakeClock:
    """固定的本地时钟助手：返回固定 datetime，并记录被调用次数。"""

    def __init__(self, when=None):
        self.when = when if when is not None else datetime(2026, 3, 1, 9, 30, 0)
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.when


# --- parse_money: 接受的类型 -------------------------------------------------


def test_parse_money_accepts_str():
    result = parse_money("5")
    assert result == Decimal("5.00")
    assert isinstance(result, Decimal)


def test_parse_money_accepts_int():
    assert parse_money(5) == Decimal("5.00")


def test_parse_money_accepts_decimal():
    assert parse_money(Decimal("2.5")) == Decimal("2.50")


def test_parse_money_returns_two_places():
    assert str(parse_money("1.5")) == "1.50"
    assert str(parse_money("0")) == "0.00"


def test_parse_money_strips_whitespace_before_parsing():
    assert parse_money("  5  ") == Decimal("5.00")


# --- parse_money: 拒绝的类型 -------------------------------------------------


def test_parse_money_rejects_bool():
    with pytest.raises(ValidationError):
        parse_money(True)


def test_parse_money_rejects_float():
    with pytest.raises(ValidationError):
        parse_money(1.5)


@pytest.mark.parametrize("value", [None, [], {}, object()])
def test_parse_money_rejects_other_types(value):
    with pytest.raises(ValidationError):
        parse_money(value)


# --- parse_money: 取值 -------------------------------------------------------


@pytest.mark.parametrize("value", ["", "   ", "abc", "5x"])
def test_parse_money_rejects_unparseable_strings(value):
    with pytest.raises(ValidationError):
        parse_money(value)


@pytest.mark.parametrize("value", ["nan", "Infinity", "-Infinity"])
def test_parse_money_rejects_non_finite(value):
    with pytest.raises(ValidationError):
        parse_money(value)


@pytest.mark.parametrize("value", ["-1", "-0.01", Decimal("-3")])
def test_parse_money_rejects_negative(value):
    with pytest.raises(ValidationError):
        parse_money(value)


@pytest.mark.parametrize("value", ["1.234", "1.230", "0.001"])
def test_parse_money_rejects_more_than_two_places(value):
    with pytest.raises(ValidationError):
        parse_money(value)


# --- round_money -------------------------------------------------------------


def test_round_money_half_up_rounds_up_on_tie():
    assert round_money(Decimal("0.125")) == Decimal("0.13")


def test_round_money_rounds_down_below_half():
    assert round_money(Decimal("2.344")) == Decimal("2.34")


def test_round_money_rounds_up_above_half():
    assert round_money(Decimal("2.345")) == Decimal("2.35")


def test_round_money_negative_tie_goes_away_from_zero():
    assert round_money(Decimal("-0.125")) == Decimal("-0.13")


def test_round_money_quantizes_to_two_places():
    assert round_money(Decimal("10")) == Decimal("10.00")


# --- format_money ------------------------------------------------------------


def test_format_money_integer_value():
    assert format_money(Decimal("3")) == "3.00"


def test_format_money_negative_value():
    assert format_money(Decimal("-3.5")) == "-3.50"


def test_format_money_rounds_before_formatting():
    assert format_money(Decimal("0.125")) == "0.13"
    assert format_money(Decimal("1.999")) == "2.00"


def test_format_money_returns_str():
    assert isinstance(format_money(Decimal("1")), str)
