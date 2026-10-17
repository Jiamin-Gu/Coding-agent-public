def normalize_email(email):
    """邮箱：去掉首尾空白、转小写。空字符串表示没有邮箱。"""
    return email.strip().lower()


def normalize_phone(phone):
    """电话：只保留数字；如果是 13 位且以 86 开头，去掉开头的 86。空字符串表示没有电话。"""
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) == 13 and digits.startswith("86"):
        digits = digits[2:]
    return digits


def find_duplicate_groups(records):
    """找出重复的客户记录。

    records：[{"id": int, "email": str, "phone": str}, ...]
    两条记录只要规范化后的邮箱相同，或者规范化后的电话相同（空值不算相同），就是同一个人；
    这种关系可以传递：A、B 邮箱相同，B、C 电话相同，则 A、B、C 是同一个人。
    返回所有包含 2 条及以上记录的分组：每组是 id 的升序列表，各组按第一个 id 升序排列。
    """
    n = len(records)
    parent = list(range(n))
    rank = [0] * n

    def find(x):
        root = x
        while parent[root] != root:
            root = parent[root]
        # 路径压缩
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        if rank[ra] < rank[rb]:
            ra, rb = rb, ra
        parent[rb] = ra
        if rank[ra] == rank[rb]:
            rank[ra] += 1

    # 记录每个规范化后的邮箱/电话首次出现的记录下标，用于合并到同一组
    email_first = {}
    phone_first = {}
    ids = [0] * n
    for i, rec in enumerate(records):
        ids[i] = rec["id"]

        email = normalize_email(rec["email"])
        if email:
            j = email_first.get(email)
            if j is None:
                email_first[email] = i
            else:
                union(i, j)

        phone = normalize_phone(rec["phone"])
        if phone:
            j = phone_first.get(phone)
            if j is None:
                phone_first[phone] = i
            else:
                union(i, j)

    grouped = {}
    for i in range(n):
        grouped.setdefault(find(i), []).append(ids[i])

    groups = [sorted(g) for g in grouped.values() if len(g) > 1]
    groups.sort()
    return groups
