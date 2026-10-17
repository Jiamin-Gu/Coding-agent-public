"""LRUCache 的测试。"""

from lru_cache import LRUCache


def test_basic_put_get():
    cache = LRUCache(2)
    cache.put(1, 1)
    cache.put(2, 2)
    assert cache.get(1) == 1
    assert cache.get(2) == 2
    assert cache.get(3) == -1  # 不存在


def test_evict_lru():
    cache = LRUCache(2)
    cache.put(1, 1)
    cache.put(2, 2)
    # 访问 1，使其成为最近使用，2 变成最久未使用
    assert cache.get(1) == 1
    cache.put(3, 3)  # 容量超限，淘汰 2
    assert cache.get(2) == -1
    assert cache.get(1) == 1
    assert cache.get(3) == 3


def test_update_existing():
    cache = LRUCache(2)
    cache.put(1, 1)
    cache.put(2, 2)
    cache.put(1, 100)  # 更新已有键，1 变成最近使用
    assert cache.get(1) == 100   # 1 仍为最近使用
    assert cache.get(2) == 2     # 访问 2 后，2 变为最近使用
    # 此时最久未使用的是 1，put 3 应淘汰 1
    cache.put(3, 3)
    assert cache.get(1) == -1
    assert cache.get(2) == 2
    assert cache.get(3) == 3


def test_capacity_one():
    cache = LRUCache(1)
    cache.put(1, 1)
    assert cache.get(1) == 1
    cache.put(2, 2)
    assert cache.get(1) == -1
    assert cache.get(2) == 2


def test_leetcode_example():
    cache = LRUCache(2)
    cache.put(1, 1)
    cache.put(2, 2)
    assert cache.get(1) == 1
    cache.put(3, 3)
    assert cache.get(2) == -1
    cache.put(4, 4)
    assert cache.get(1) == -1
    assert cache.get(3) == 3
    assert cache.get(4) == 4


def test_order_after_get():
    cache = LRUCache(3)
    cache.put(1, 1)
    cache.put(2, 2)
    cache.put(3, 3)
    cache.get(1)      # 顺序: 1, 3, 2 (最近 -> 最久)
    cache.get(2)      # 顺序: 2, 1, 3
    cache.put(4, 4)   # 淘汰 3
    assert cache.get(3) == -1
    assert cache.get(1) == 1
    assert cache.get(2) == 2
    assert cache.get(4) == 4


def test_invalid_capacity():
    for bad in (0, -1):
        try:
            LRUCache(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"capacity={bad} 应该抛出 ValueError")


if __name__ == "__main__":
    tests = [obj for name, obj in sorted(globals().items())
             if name.startswith("test_") and callable(obj)]
    for fn in tests:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n全部 {len(tests)} 个测试通过")
