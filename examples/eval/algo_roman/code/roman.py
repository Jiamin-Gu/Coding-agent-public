"""阿拉伯数字与罗马数字之间的转换（支持 1 到 3999）。"""

# 罗马数字的规范写法表（贪心法使用），按数值从大到小排列。
_TABLE = [
    (1000, "M"),
    (900, "CM"),
    (500, "D"),
    (400, "CD"),
    (100, "C"),
    (90, "XC"),
    (50, "L"),
    (40, "XL"),
    (10, "X"),
    (9, "IX"),
    (5, "V"),
    (4, "IV"),
    (1, "I"),
]

# 单个罗马数字字符对应的数值。
_VALUES = {
    "I": 1,
    "V": 5,
    "X": 10,
    "L": 50,
    "C": 100,
    "D": 500,
    "M": 1000,
}

# 合法的减法组合（只有这六种）。
_SUBTRACTIVE = {"IV", "IX", "XL", "XC", "CD", "CM"}


def to_roman(n: int) -> str:
    """把 1 到 3999 的整数转换为罗马数字。

    例如 1994 -> "MCMXCIV"。超出范围或类型不合法时抛出 ValueError。
    """
    if isinstance(n, bool) or not isinstance(n, int):
        raise ValueError(f"需要整数，收到 {type(n).__name__}")
    if n < 1 or n > 3999:
        raise ValueError(f"超出范围（1-3999）：{n}")

    parts = []
    for value, symbol in _TABLE:
        while n >= value:
            parts.append(symbol)
            n -= value
    return "".join(parts)


def from_roman(s: str) -> int:
    """把罗马数字转换为整数。

    只接受规范写法，任何不合法或非规范的输入（如 "IIII"、"VX"、
    "IC"、空字符串、小写字母）都会抛出 ValueError。
    """
    if not isinstance(s, str) or not s:
        raise ValueError("需要非空字符串")

    total = 0
    i = 0
    length = len(s)
    while i < length:
        ch = s[i]
        if ch not in _VALUES:
            raise ValueError(f"非法字符：{ch!r}")
        if i + 1 < length and s[i:i + 2] in _SUBTRACTIVE:
            total += _VALUES[s[i + 1]] - _VALUES[ch]
            i += 2
        else:
            total += _VALUES[ch]
            i += 1

    # 用规范写法重新编码进行校验，可排除 "IIII"、"VX"、"IC" 等不合法形式。
    if not 1 <= total <= 3999 or to_roman(total) != s:
        raise ValueError(f"不规范的罗马数字：{s!r}")

    return total
