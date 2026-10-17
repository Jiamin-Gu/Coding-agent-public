"""简单的统计函数。"""


def mean(values):
    return sum(values) / len(values)


def median(values):
    values.sort()
    mid = len(values) // 2
    return values[mid]


def mode(values):
    counts = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    return max(counts)
