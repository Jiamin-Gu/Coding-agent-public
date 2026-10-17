def normalize_email(email):
    return email.strip().lower()


def normalize_phone(phone):
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) == 13 and digits.startswith("86"):
        digits = digits[2:]
    return digits


def find_duplicate_groups(records):
    parent = {}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    first_by_key = {}
    for r in records:
        parent.setdefault(r["id"], r["id"])
        for key in (("e", normalize_email(r["email"])), ("p", normalize_phone(r["phone"]))):
            if not key[1]:
                continue
            if key in first_by_key:
                union(first_by_key[key], r["id"])
            else:
                first_by_key[key] = r["id"]
    groups = {}
    for i in parent:
        groups.setdefault(find(i), []).append(i)
    return sorted(sorted(g) for g in groups.values() if len(g) > 1)
