import re
from decimal import ROUND_HALF_UP, Decimal

UNITS = {"d": 86400, "h": 3600, "m": 60, "s": 1}
UNIT_ORDER = ("d", "h", "m", "s")

# 一个"数值+单位"片段：数值为整数或小数（小数点前后均须有数字）。
_UNIT_PART = re.compile(r"(\d+(?:\.\d+)?)([dhms])", re.IGNORECASE)
# 不带单位的数值（只能单独出现）。
_PLAIN_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def _round_seconds(value):
    """把 Decimal 秒数按四舍五入（0.5 进位）取整。"""
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def parse_duration(text):
    """解析时长字符串，返回秒数（int）。

    规则：
    - 由若干"数值+单位"组成，单位是 d（天）、h（小时）、m（分钟）、s（秒），不区分大小写。
      例如 "1h30m"、"2d 3h"、"1H 5M 10S"
    - 各部分之间可以有任意空白；字符串首尾的空白忽略
    - 数值可以是整数或小数（小数点前后都必须有数字，例如 1.5h），结果四舍五入到整秒（0.5 进位）
    - 只有一个数字、没有单位时表示秒："90" → 90、"2.5" → 3；没有单位的数字只能单独出现
    - 每个单位最多出现一次，并且必须按 d、h、m、s 的顺序出现，否则抛出 ValueError
      （"30m1h"、"1h1h" 都不合法）
    - 空字符串（或只有空白）、负数、未知单位、多余的字符，都抛出 ValueError
    """
    if not isinstance(text, str):
        raise ValueError(f"非法时长: {text!r}")

    s = text.strip()
    if not s:
        raise ValueError("时长不能为空")

    # 只有数字、没有单位时表示秒。
    if _PLAIN_NUMBER.fullmatch(s):
        return _round_seconds(Decimal(s))

    total = Decimal(0)
    seen = set()
    last_order = -1
    pos = 0
    length = len(s)

    while pos < length:
        # 跳过各部分之间的任意空白。
        while pos < length and s[pos].isspace():
            pos += 1
        if pos >= length:
            break

        match = _UNIT_PART.match(s, pos)
        if match is None:
            raise ValueError(f"非法时长: {text!r}")

        value = Decimal(match.group(1))
        unit = match.group(2).lower()

        if unit in seen:
            raise ValueError(f"单位重复: {unit!r}")
        order = UNIT_ORDER.index(unit)
        if order <= last_order:
            raise ValueError(f"单位顺序错误: {unit!r}")
        seen.add(unit)
        last_order = order

        total += value * UNITS[unit]
        pos = match.end()

    return _round_seconds(total)


def format_duration(seconds):
    """把非负整数秒格式化成最简的时长字符串。

    - 省略为 0 的单位：5400 → "1h30m"、90061 → "1d1h1m1s"、45 → "45s"、86400 → "1d"
    - 0 → "0s"
    - 负数或非整数抛出 ValueError
    - 对任意非负整数 n，parse_duration(format_duration(n)) == n
    """
    if isinstance(seconds, float):
        if not seconds.is_integer():
            raise ValueError(f"非整数秒: {seconds!r}")
        seconds = int(seconds)
    elif not isinstance(seconds, int):
        raise ValueError(f"非整数秒: {seconds!r}")

    if seconds < 0:
        raise ValueError(f"负数秒: {seconds!r}")

    parts = []
    for unit in UNIT_ORDER:
        n, seconds = divmod(seconds, UNITS[unit])
        if n:
            parts.append(f"{n}{unit}")
    return "".join(parts) or "0s"
