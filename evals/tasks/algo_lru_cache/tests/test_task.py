import time

from lru_cache import LRUCache


def test_basic_eviction():
    c = LRUCache(2)
    c.put(1, 1)
    c.put(2, 2)
    assert c.get(1) == 1
    c.put(3, 3)          # 淘汰 2
    assert c.get(2) == -1
    c.put(4, 4)          # 淘汰 1
    assert c.get(1) == -1
    assert c.get(3) == 3
    assert c.get(4) == 4


def test_update_marks_recent():
    c = LRUCache(2)
    c.put(1, 1)
    c.put(2, 2)
    c.put(1, 10)         # 更新后 1 变成最近使用
    c.put(3, 3)          # 淘汰 2
    assert c.get(1) == 10
    assert c.get(2) == -1


def test_capacity_one():
    c = LRUCache(1)
    c.put(1, 1)
    c.put(2, 2)
    assert c.get(1) == -1
    assert c.get(2) == 2


def test_performance_is_not_linear():
    c = LRUCache(50_000)
    start = time.perf_counter()
    for i in range(200_000):
        c.put(i, i)
        c.get(i - 100)
    assert time.perf_counter() - start < 3
