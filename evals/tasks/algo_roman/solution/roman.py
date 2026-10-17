VALUES = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
          (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]


def to_roman(n):
    if not isinstance(n, int) or not 1 <= n <= 3999:
        raise ValueError("超出范围")
    out = []
    for value, symbol in VALUES:
        while n >= value:
            out.append(symbol)
            n -= value
    return "".join(out)


def from_roman(s):
    if not s or not isinstance(s, str):
        raise ValueError("不合法")
    total, i = 0, 0
    for value, symbol in VALUES:
        while s.startswith(symbol, i):
            total += value
            i += len(symbol)
    if i != len(s) or not 1 <= total <= 3999 or to_roman(total) != s:
        raise ValueError("不合法")
    return total
