"""金额解析与格式化工具。

内部一律使用 :class:`decimal.Decimal` 做精确计算，绝不使用 ``float``。
对外金额统一为保留两位小数的字符串（例如 ``"0.30"``、``"-12.00"``）。
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

#: 最小金额单位（分）。
CENT = Decimal("0.01")


def parse_amount(value) -> Decimal:
    """把 ``str`` / ``int`` / ``Decimal`` 解析为合法的正金额。

    合法条件：可解析为有限数、``value > 0`` 且最多两位小数。
    其它类型、``bool``、``0``、负数、``"abc"``、``"1.234"``、``"1e-3"``
    等一律抛出 :class:`ValueError`。
    """
    if isinstance(value, bool):
        raise ValueError(f"非法金额: {value!r}")
    if isinstance(value, Decimal):
        d = value
    elif isinstance(value, int):
        d = Decimal(value)
    elif isinstance(value, str):
        try:
            d = Decimal(value)
        except (InvalidOperation, ArithmeticError, ValueError):
            raise ValueError(f"非法金额: {value!r}") from None
    else:
        raise ValueError(f"非法金额: {value!r}")

    if not d.is_finite():
        raise ValueError(f"非法金额: {value!r}")
    if d <= 0:
        raise ValueError(f"金额必须为正数: {value!r}")

    try:
        quantized = d.quantize(CENT)
    except (InvalidOperation, ArithmeticError):
        raise ValueError(f"非法金额: {value!r}") from None
    if d != quantized:
        raise ValueError(f"金额最多两位小数: {value!r}")
    return quantized


def format_money(value) -> str:
    """把金额格式化为保留两位小数的字符串。"""
    if not isinstance(value, Decimal):
        value = Decimal(value)
    quantized = value.quantize(CENT)
    if quantized == 0:
        quantized = abs(quantized)
    return str(quantized)
