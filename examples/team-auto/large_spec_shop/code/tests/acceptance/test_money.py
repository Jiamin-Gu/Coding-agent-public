from decimal import Decimal

import pytest

from shopkit import Shop
from shopkit.errors import ShopError, ValidationError
from shopkit.money import format_money, parse_money, round_money


@pytest.mark.parametrize(
    "value,expected",
    [
        ("5", Decimal("5.00")),
        (" 1.5 ", Decimal("1.50")),
        ("0", Decimal("0.00")),
        (3, Decimal("3.00")),
        (Decimal("2.25"), Decimal("2.25")),
        ("12.30", Decimal("12.30")),
        ("1E+2", Decimal("100.00")),
    ],
)
def test_parse_money_ok(value, expected):
    assert parse_money(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        True,
        False,
        1.5,
        None,
        [],
        {},
        "abc",
        "",
        "1.234",
        "-1",
        "-0.01",
        "nan",
        "inf",
        "Infinity",
        "NaN",
    ],
)
def test_parse_money_bad(value):
    with pytest.raises(ValidationError):
        parse_money(value)


def test_parse_money_bool_is_not_int():
    with pytest.raises(ValidationError):
        parse_money(True)


def test_round_money_half_up():
    assert round_money(Decimal("0.125")) == Decimal("0.13")
    assert round_money(Decimal("0.135")) == Decimal("0.14")
    assert round_money(Decimal("2.345")) == Decimal("2.35")
    assert round_money(Decimal("1")) == Decimal("1.00")


def test_format_money():
    assert format_money(Decimal("3")) == "3.00"
    assert format_money(Decimal("-3.5")) == "-3.50"
    assert format_money(Decimal("0.125")) == "0.13"


def test_exceptions_hierarchy():
    assert issubclass(ValidationError, ShopError)
    assert issubclass(ShopError, Exception)


def test_shop_importable_from_package():
    assert Shop is not None
