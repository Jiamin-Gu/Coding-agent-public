def _check(values):
    if not values:
        raise ValueError("列表不能为空")


def mean(values):
    _check(values)
    return sum(values) / len(values)


def median(values):
    _check(values)
    s = sorted(values)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2


def mode(values):
    _check(values)
    counts = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    best = max(counts.values())
    return min(v for v, c in counts.items() if c == best)
