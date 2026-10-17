from __future__ import annotations

from ..errors import NotFoundError
from ..models.branch import Branch


class BranchRepo:
    """分馆的存储（保存在内存里）。"""

    def __init__(self):
        self._items: dict[int, Branch] = {}
        self._next_id = 1

    def add(self, **fields) -> Branch:
        item = Branch(id=self._next_id, **fields)
        self._items[item.id] = item
        self._next_id += 1
        return item

    def get(self, item_id) -> Branch:
        if item_id not in self._items:
            raise NotFoundError(f"分馆不存在：{item_id}")
        return self._items[item_id]

    def list(self) -> list[Branch]:
        return [self._items[k] for k in sorted(self._items)]

    def update(self, item_id, **changes) -> Branch:
        item = self.get(item_id)
        for field, value in changes.items():
            if field == "id" or not hasattr(item, field):
                raise ValueError(f"不能修改字段：{field}")
            setattr(item, field, value)
        return item

    def delete(self, item_id) -> None:
        self.get(item_id)
        del self._items[item_id]
