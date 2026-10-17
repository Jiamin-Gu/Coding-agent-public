import csv
import sys
from collections import defaultdict
from decimal import Decimal


def summarize(path):
    totals = defaultdict(Decimal)
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if not row.get("date"):
                continue
            amount = Decimal(row["amount"].replace(",", "").strip())
            totals[(row["date"].strip()[:7], row["region"].strip())] += amount
    return [f"{m} {r} {v:.2f}" for (m, r), v in sorted(totals.items())]


if __name__ == "__main__":
    print("\n".join(summarize(sys.argv[1])))
