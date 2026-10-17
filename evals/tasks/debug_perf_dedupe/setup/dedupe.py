def normalize_email(email):
    """邮箱：去掉首尾空白、转小写。空字符串表示没有邮箱。"""
    return email.lower()


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
    groups = []
    used = set()
    for i, a in enumerate(records):
        if a["id"] in used:
            continue
        group = [a["id"]]
        for b in records[i + 1:]:
            if b["id"] in used:
                continue
            ea, eb = normalize_email(a["email"]), normalize_email(b["email"])
            pa, pb = normalize_phone(a["phone"]), normalize_phone(b["phone"])
            if (ea and ea == eb) or (pa and pa == pb):
                group.append(b["id"])
                used.add(b["id"])
        if len(group) > 1:
            used.add(a["id"])
            groups.append(sorted(group))
    return sorted(groups)
