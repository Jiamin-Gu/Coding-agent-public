"""Monetary helpers.  All amounts are ``decimal.Decimal``; floats are rejected."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from .errors import ValidationError

_TWO_PLACES = Decimal("0.01")
_ZERO = Decimal("0.00")


def round_money(d: Decimal) -> Decimal:
    """Round ``d`` to two decimal places using ROUND_HALF_UP."""
    return d.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


def format_money(d: Decimal) -> str:
    """Format ``d`` as a string with exactly two decimal places."""
    if d == 0:
        return "0.00"
    return str(round_money(d))


def parse_money(value) -> Decimal:
    """Parse ``value`` (str/int/Decimal) into a non-negative 2-decimal Decimal."""
    if isinstance(value, bool):
        raise ValidationError("money value must not be a bool")
    if isinstance(value, Decimal):
        d = value
    elif isinstance(value, int):
        d = Decimal(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValidationError("money value must not be empty")
        try:
            d = Decimal(text)
        except InvalidOperation:
            raise ValidationError("money value is not a valid number")
    else:
        raise ValidationError("money value must be str, int or Decimal")

    if not d.is_finite():
        raise ValidationError("money value must be finite")
    if d < 0:
        raise ValidationError("money value must be >= 0")
    if -d.as_tuple().exponent > 2:
        raise ValidationError("money value must have at most 2 decimals")
    if d == 0:
        return _ZERO
    return round_money(d)
