在 lru_cache.py 中实现 LRUCache 类：

- `LRUCache(capacity: int)`：创建容量为 capacity 的缓存
- `get(key) -> int`：键存在时返回对应的值，并把它标记为最近使用；不存在时返回 -1
- `put(key, value) -> None`：插入或更新键值，并标记为最近使用；超过容量时，淘汰最久未使用的键

get 和 put 的时间复杂度都要求是 O(1)。写完后自己写测试验证。
