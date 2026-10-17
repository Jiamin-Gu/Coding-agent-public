import re
from decimal import ROUND_HALF_UP, Decimal

UNITS = {"d": 86400, "h": 3600, "m": 60, "s": 1}
ORDER = "dhms"
NUM = r"\d+(?:\.\d+)?"
PART = re.compile(rf"\s*({NUM})([dhms])", re.IGNORECASE)


def _round(value):
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def parse_duration(text):
    if not isinstance(text, str):
        raise ValueError("需要字符串")
    s = text.strip()
    if not s:
        raise ValueError("空字符串")
    if re.fullmatch(NUM, s):
        return _round(Decimal(s))
    total, pos, last = Decimal(0), 0, -1
    while pos < len(s):
        m = PART.match(s, pos)
        if not m:
            raise ValueError(f"无法解析：{text!r}")
        idx = ORDER.index(m.group(2).lower())
        if idx <= last:
            raise ValueError("单位重复或顺序错误")
        last = idx
        total += Decimal(m.group(1)) * UNITS[ORDER[idx]]
        pos = m.end()
    return _round(total)


def format_duration(seconds):
    if isinstance(seconds, bool) or not isinstance(seconds, int) or seconds < 0:
        raise ValueError("需要非负整数")
    if seconds == 0:
        return "0s"
    parts = []
    for unit, size in UNITS.items():
        n, seconds = divmod(seconds, size)
        if n:
            parts.append(f"{n}{unit}")
    return "".join(parts)
