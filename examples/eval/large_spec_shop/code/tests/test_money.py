from decimal import Decimal

import pytest

from shopkit.errors import ValidationError
from shopkit.money import format_money, parse_money, round_money


def test_parse_money_basic():
    assert parse_money("5") == Decimal("5.00")
    assert parse_money(5) == Decimal("5.00")
    assert parse_money(Decimal("5")) == Decimal("5.00")
    assert parse_money(" 1.5 ") == Decimal("1.50")
    assert parse_money("0") == Decimal("0.00")


def test_parse_money_returns_two_places():
    value = parse_money("3.5")
    assert str(value) == "3.50"
    assert value.as_tuple().exponent == -2


@pytest.mark.parametrize("bad", ["1.234", "-1", "abc", "", "  ", "NaN", "Infinity"])
def test_parse_money_invalid_strings(bad):
    with pytest.raises(ValidationError):
        parse_money(bad)


@pytest.mark.parametrize("bad", [True, False, 1.0, 0.5, None, [], {}, object()])
def test_parse_money_invalid_types(bad):
    with pytest.raises(ValidationError):
        parse_money(bad)


def test_round_money_half_up():
    assert round_money(Decimal("0.125")) == Decimal("0.13")
    assert round_money(Decimal("0.135")) == Decimal("0.14")
    assert round_money(Decimal("0.124")) == Decimal("0.12")
    assert round_money(Decimal("2")) == Decimal("2.00")


def test_format_money():
    assert format_money(Decimal("3")) == "3.00"
    assert format_money(Decimal("-3.5")) == "-3.50"
    assert format_money(Decimal("12.3")) == "12.30"
    assert format_money(Decimal("12.345")) == "12.35"
