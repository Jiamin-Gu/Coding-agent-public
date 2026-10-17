"""简单的统计函数。"""


def mean(values):
    if not values:
        raise ValueError("mean() 需要非空序列")
    return sum(values) / len(values)


def median(values):
    if not values:
        raise ValueError("median() 需要非空序列")
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def mode(values):
    if not values:
        raise ValueError("mode() 需要非空序列")
    counts = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    max_count = max(counts.values())
    return min(v for v, c in counts.items() if c == max_count)
