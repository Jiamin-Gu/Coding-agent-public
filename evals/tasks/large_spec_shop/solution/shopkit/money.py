from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from .errors import ValidationError

CENT = Decimal("0.01")


def parse_money(value) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValidationError(f"invalid money type: {value!r}")
    try:
        d = Decimal(value.strip() if isinstance(value, str) else value)
    except (InvalidOperation, ValueError):
        raise ValidationError(f"invalid money: {value!r}") from None
    if not d.is_finite() or d < 0:
        raise ValidationError(f"invalid money: {value!r}")
    try:
        q = d.quantize(CENT)
    except InvalidOperation:
        raise ValidationError(f"invalid money: {value!r}") from None
    if q != d:
        raise ValidationError(f"too many decimals: {value!r}")
    return q + 0


def round_money(d: Decimal) -> Decimal:
    return d.quantize(CENT, rounding=ROUND_HALF_UP)


def format_money(d: Decimal) -> str:
    return f"{round_money(d):.2f}"
