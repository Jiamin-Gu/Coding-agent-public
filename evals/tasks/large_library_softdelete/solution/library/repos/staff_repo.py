from __future__ import annotations

from ..errors import NotFoundError
from ..models.staff import Staff


class StaffRepo:
    """员工的存储（保存在内存里）。"""

    def __init__(self, audit=None, clock=None):
        self._items: dict[int, Staff] = {}
        self._next_id = 1
        self._audit = audit
        self._clock = clock

    def _log(self, item_id, action):
        if self._audit is not None:
            self._audit.record("staff", item_id, action)

    def add(self, **fields) -> Staff:
        item = Staff(id=self._next_id, **fields)
        self._items[item.id] = item
        self._next_id += 1
        self._log(item.id, "create")
        return item

    def get(self, item_id, include_deleted=False) -> Staff:
        item = self._items.get(item_id)
        if item is None or (item.deleted and not include_deleted):
            raise NotFoundError(f"员工不存在：{item_id}")
        return item

    def list(self, include_deleted=False) -> list[Staff]:
        return [self._items[k] for k in sorted(self._items) if include_deleted or not self._items[k].deleted]

    def update(self, item_id, **changes) -> Staff:
        item = self.get(item_id)
        for field, value in changes.items():
            if field == "id" or not hasattr(item, field):
                raise ValueError(f"不能修改字段：{field}")
            setattr(item, field, value)
        self._log(item_id, "update")
        return item

    def delete(self, item_id) -> None:
        item = self.get(item_id)
        item.deleted = True
        item.deleted_at = self._clock.now() if self._clock else None
        self._log(item_id, "delete")

    def restore(self, item_id) -> Staff:
        item = self._items.get(item_id)
        if item is None or not item.deleted:
            raise NotFoundError(f"没有可恢复的员工：{item_id}")
        item.deleted = False
        item.deleted_at = None
        self._log(item_id, "restore")
        return item

    def by_branch(self, branch_id) -> list[Staff]:
        """某个分馆的所有员工。"""
        return [i for i in self.list() if i.branch_id == branch_id]
