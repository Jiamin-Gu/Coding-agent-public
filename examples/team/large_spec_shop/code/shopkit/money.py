"""金额工具：解析、舍入、格式化。

金额在内部一律用 :class:`decimal.Decimal` 计算，**不能用 float**。
返回值里的金额一律是保留两位小数的字符串。
"""

from decimal import Decimal, ROUND_HALF_UP

from shopkit.errors import ValidationError

_TWO_PLACES = Decimal("0.01")


def parse_money(value) -> Decimal:
    """把 ``str`` / ``int`` / ``Decimal`` 解析成保留两位小数的 ``Decimal``。

    - ``bool``、``float`` 和其他类型一律 :class:`ValidationError`
    - 字符串先去掉首尾空白再解析，解析失败 :class:`ValidationError`
    - 必须是有限数（不能是 NaN、Infinity）、``>= 0``、最多两位小数
    - 返回保留两位小数的 ``Decimal``，例如 ``parse_money("5")`` -> ``Decimal("5.00")``
    """
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValidationError(f"金额必须是 str/int/Decimal，不能是 {type(value).__name__}")

    if isinstance(value, str):
        value = value.strip()
        if value == "":
            raise ValidationError("金额字符串为空")
        try:
            d = Decimal(value)
        except Exception:
            raise ValidationError(f"无法解析金额：{value!r}") from None
    else:
        d = Decimal(value)

    if not d.is_finite():
        raise ValidationError(f"金额必须是有限数：{value!r}")
    if d < 0:
        raise ValidationError(f"金额不能为负：{value!r}")
    exponent = d.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -2:
        raise ValidationError(f"金额最多两位小数：{value!r}")

    try:
        return d.quantize(_TWO_PLACES)
    except ArithmeticError:
        # 数量级过大导致量化超出上下文精度，同样按取值不合法处理
        raise ValidationError(f"金额超出可表示范围：{value!r}") from None


def round_money(d: Decimal) -> Decimal:
    """四舍五入到两位小数（``ROUND_HALF_UP``）。"""
    try:
        return d.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)
    except ArithmeticError:
        raise ValidationError(f"金额超出可表示范围：{d!r}") from None


def format_money(d: Decimal) -> str:
    """先 ``round_money``，再格式化成两位小数的字符串。"""
    return str(round_money(d))