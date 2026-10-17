from __future__ import annotations

from ..clock import Clock
from ..errors import NotFoundError


class BaseRepo:
    """所有实体存储的基类（保存在内存里），提供软删除、恢复与审计。"""

    model = None  # 子类设置：对应的实体数据类
    label = "实体"  # 子类设置：用于报错文案 '<label>不存在：<id>'
    entity_type = None  # 子类设置：等于 Library.repos 的键，例如 'book'

    def __init__(self, clock=None, audit=None):
        self._items: dict[int, model] = {}
        self._next_id = 1
        self.clock = clock or Clock()
        self.audit = audit

    def add(self, **fields):
        item = self.model(id=self._next_id, **fields)
        self._items[item.id] = item
        self._next_id += 1
        self._record("create", item.id)
        return item

    def get(self, item_id, include_deleted=False):
        if item_id not in self._items:
            raise NotFoundError(f"{self.label}不存在：{item_id}")
        item = self._items[item_id]
        if item.deleted and not include_deleted:
            raise NotFoundError(f"{self.label}不存在：{item_id}")
        return item

    def list(self, include_deleted=False):
        items = [self._items[k] for k in sorted(self._items)]
        if include_deleted:
            return items
        return [i for i in items if not i.deleted]

    def update(self, item_id, **changes):
        item = self.get(item_id)
        for field, value in changes.items():
            if field == "id" or not hasattr(item, field):
                raise ValueError(f"不能修改字段：{field}")
            setattr(item, field, value)
        self._record("update", item.id)
        return item

    def delete(self, item_id) -> None:
        item = self.get(item_id)
        item.deleted = True
        item.deleted_at = self.clock.now()
        self._record("delete", item.id)

    def restore(self, item_id):
        if item_id not in self._items:
            raise NotFoundError(f"{self.label}不存在：{item_id}")
        item = self._items[item_id]
        if not item.deleted:
            raise NotFoundError(f"{self.label}不存在：{item_id}")
        item.deleted = False
        item.deleted_at = None
        self._record("restore", item.id)
        return item

    def _record(self, action, entity_id) -> None:
        if self.audit is not None:
            self.audit.record(self.entity_type, entity_id, action)
