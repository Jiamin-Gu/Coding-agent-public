"""金额解析与格式化工具。

金额在内部一律使用 :class:`decimal.Decimal` 计算，不使用 float。
"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from .errors import ValidationError

_TWO_PLACES = Decimal("0.01")


def parse_money(value) -> Decimal:
    """把 ``value`` 解析成一个 >= 0、最多两位小数的 :class:`Decimal`。

    接受 ``str``、``int``、``Decimal``；``bool``、``float`` 和其他类型一律
    抛出 :class:`ValidationError`。
    """
    if isinstance(value, bool):
        raise ValidationError("金额不能是 bool: {!r}".format(value))

    if isinstance(value, Decimal):
        d = value
    elif isinstance(value, int):
        d = Decimal(value)
    elif isinstance(value, str):
        text = value.strip()
        try:
            d = Decimal(text)
        except (InvalidOperation, ValueError):
            raise ValidationError("无法解析金额: {!r}".format(value))
    else:
        raise ValidationError("不支持的金额类型: {!r}".format(value))

    if not d.is_finite():
        raise ValidationError("金额必须是有限数: {!r}".format(value))
    if d < 0:
        raise ValidationError("金额不能为负数: {!r}".format(value))
    if -d.as_tuple().exponent > 2:
        raise ValidationError("金额最多两位小数: {!r}".format(value))

    return d.quantize(_TWO_PLACES)


def round_money(d: Decimal) -> Decimal:
    """四舍五入（``ROUND_HALF_UP``）到两位小数。"""
    return d.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


def format_money(d: Decimal) -> str:
    """先四舍五入到两位小数，再格式化成两位小数的字符串。"""
    return str(round_money(d))
