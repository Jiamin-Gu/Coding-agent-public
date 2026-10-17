import random
import time

from dedupe import find_duplicate_groups, normalize_email, normalize_phone


def rec(i, email="", phone=""):
    return {"id": i, "email": email, "phone": phone}


def test_normalization():
    assert normalize_email("  Alice@Example.COM ") == "alice@example.com"
    assert normalize_phone("+86 138-0000-1111") == "13800001111"
    assert normalize_phone("(010) 1234 5678") == "01012345678"


def test_transitive_groups():
    records = [rec(4, "d@x.com", "222"), rec(1, "a@x.com", "111"), rec(2, " A@X.com", "333"),
               rec(3, "c@x.com", "333"), rec(5, "c@x.com", ""), rec(9, "z@x.com", "999")]
    # 1-2 邮箱相同，2-3 电话相同，3-5 邮箱相同 → [1,2,3,5]
    assert find_duplicate_groups(records) == [[1, 2, 3, 5]]


def test_empty_values_do_not_match():
    records = [rec(1, "", ""), rec(2, "", ""), rec(3, "a@x.com", ""), rec(4, "", "+86 13800001111"),
               rec(5, "", "13800001111")]
    assert find_duplicate_groups(records) == [[4, 5]]


def test_multiple_groups_sorted():
    records = [rec(10, "b@x.com"), rec(3, "b@x.com"), rec(7, "a@x.com"), rec(1, "a@x.com"), rec(5, "a@x.com")]
    assert find_duplicate_groups(records) == [[1, 5, 7], [3, 10]]


def test_chain_built_in_reverse_order():
    # 链条的连接点出现在后面，逐条比较的写法会漏掉
    records = [rec(1, "a@x.com", "1"), rec(2, "b@x.com", "2"), rec(3, "a@x.com", "2")]
    assert find_duplicate_groups(records) == [[1, 2, 3]]


def test_performance_200k():
    rng = random.Random(42)
    records = []
    for i in range(200_000):
        email = f"user{rng.randrange(180_000)}@example.com" if rng.random() < 0.8 else ""
        phone = str(13_000_000_000 + rng.randrange(180_000)) if rng.random() < 0.6 else ""
        records.append(rec(i, email, phone))
    start = time.perf_counter()
    groups = find_duplicate_groups(records)
    assert time.perf_counter() - start < 3
    assert groups and all(len(g) >= 2 and g == sorted(g) for g in groups)
    assert sum(len(g) for g in groups) == len({i for g in groups for i in g})   # 每条记录最多在一组
