"""Parse application logs and compute simple statistics."""

import re

# 例：2026-09-30 10:00:01 INFO user=alice action=login latency=120ms
# 可选尾部：error="timeout"
LINE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}) "
    r"(\d{2}:\d{2}:\d{2}) "
    r"([A-Z]+) "
    r"user=(\S+) "
    r"action=(\S+) "
    r"latency=(\d+)ms"
    r'(?:\s+error="[^"]*")?$'
)


def analyze(path: str) -> dict:
    total = 0
    by_level = {}
    error_users = set()
    latency_sum = 0
    avg_latency_ms = 0.0
    slowest = None
    slowest_latency = -1

    with open(path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue

            match = LINE_RE.match(line)
            if match is None:
                continue

            _, _, level, user, action, latency_str = match.groups()
            latency = int(latency_str)

            total += 1
            by_level[level] = by_level.get(level, 0) + 1
            latency_sum += latency

            if level == "ERROR":
                error_users.add(user)

            if latency > slowest_latency:
                slowest_latency = latency
                slowest = action

    if total:
        avg_latency_ms = round(latency_sum / total, 1)

    return {
        "total": total,
        "by_level": by_level,
        "error_users": sorted(error_users),
        "avg_latency_ms": avg_latency_ms,
        "slowest": slowest,
    }
