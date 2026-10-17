"""基于哈希表 + 双向链表实现的 LRU 缓存。

哈希表提供 O(1) 的查找，双向链表维护访问顺序：
链表头部是最近使用的节点，尾部是最久未使用的节点。
因此 get / put 的时间复杂度均为 O(1)。
"""


class _Node:
    """双向链表节点。"""

    __slots__ = ("key", "value", "prev", "next")

    def __init__(self, key=0, value=0):
        self.key = key
        self.value = value
        self.prev = None
        self.next = None


class LRUCache:
    def __init__(self, capacity: int):
        if capacity <= 0:
            raise ValueError("capacity must be a positive integer")
        self.capacity = capacity
        self.cache = {}  # key -> _Node

        # 使用哨兵节点，避免处理头尾的边界情况
        self.head = _Node()  # 哨兵：head.next 是最近使用的节点
        self.tail = _Node()  # 哨兵：tail.prev 是最久未使用的节点
        self.head.next = self.tail
        self.tail.prev = self.head

    def _remove(self, node: _Node) -> None:
        """把节点从链表中摘下。"""
        node.prev.next = node.next
        node.next.prev = node.prev

    def _add_to_head(self, node: _Node) -> None:
        """把节点插入到链表头部（标记为最近使用）。"""
        node.prev = self.head
        node.next = self.head.next
        self.head.next.prev = node
        self.head.next = node

    def _move_to_head(self, node: _Node) -> None:
        self._remove(node)
        self._add_to_head(node)

    def get(self, key) -> int:
        if key not in self.cache:
            return -1
        node = self.cache[key]
        self._move_to_head(node)
        return node.value

    def put(self, key, value) -> None:
        if key in self.cache:
            node = self.cache[key]
            node.value = value
            self._move_to_head(node)
            return

        node = _Node(key, value)
        self.cache[key] = node
        self._add_to_head(node)

        if len(self.cache) > self.capacity:
            # 淘汰最久未使用的节点（链表尾部）
            lru = self.tail.prev
            self._remove(lru)
            del self.cache[lru.key]
