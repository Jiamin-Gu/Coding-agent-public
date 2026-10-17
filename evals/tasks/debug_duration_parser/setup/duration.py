import re

UNITS = {"d": 86400, "h": 3600, "m": 60, "s": 1}


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
    total = 0
    for value, unit in re.findall(r"(\d+)([dhms])", text):
        total += int(value) * UNITS[unit]
    return total


def format_duration(seconds):
    """把非负整数秒格式化成最简的时长字符串。

    - 省略为 0 的单位：5400 → "1h30m"、90061 → "1d1h1m1s"、45 → "45s"、86400 → "1d"
    - 0 → "0s"
    - 负数或非整数抛出 ValueError
    - 对任意非负整数 n，parse_duration(format_duration(n)) == n
    """
    parts = []
    for unit, size in UNITS.items():
        n, seconds = divmod(seconds, size)
        parts.append(f"{n}{unit}")
    return "".join(parts)
