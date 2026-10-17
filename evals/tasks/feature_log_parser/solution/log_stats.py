import re

LINE = re.compile(r"^\S+ \S+ (?P<level>[A-Z]+) user=(?P<user>\S+) action=(?P<action>\S+) latency=(?P<ms>\d+)ms")


def analyze(path):
    total, by_level, error_users, latencies = 0, {}, set(), []
    slowest, slowest_ms = None, -1
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = LINE.match(line.strip())
            if not m:
                continue
            total += 1
            by_level[m["level"]] = by_level.get(m["level"], 0) + 1
            if m["level"] == "ERROR":
                error_users.add(m["user"])
            ms = int(m["ms"])
            latencies.append(ms)
            if ms > slowest_ms:
                slowest, slowest_ms = m["action"], ms
    avg = round(sum(latencies) / len(latencies), 1) if latencies else 0.0
    return {"total": total, "by_level": by_level, "error_users": sorted(error_users),
            "avg_latency_ms": avg, "slowest": slowest}
