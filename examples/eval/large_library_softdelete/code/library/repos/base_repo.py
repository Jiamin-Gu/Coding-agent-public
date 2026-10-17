from __future__ import annotations

from ..audit import AuditLog
from ..clock import Clock
from ..errors import NotFoundError


class BaseRepo:
    """所有存储的公共实现（软删除、恢复、审计）。

    子类需要设置 ``model_cls``（实体类）和 ``entity_type``（实体名，即
    ``Library.repos`` 的键）、``label``（用于错误信息的中文名）。
    """

    model_cls = None
    entity_type = None
    label = "实体"

    def __init__(self, clock=None, audit=None, entity_type=None):
        self._items: dict[int, object] = {}
        self._next_id = 1
        self._clock = clock or Clock()
        self._audit: AuditLog | None = audit
        if entity_type is not None:
            self.entity_type = entity_type

    def _log(self, action: str, item) -> None:
        if self._audit is not None:
            self._audit.record(self.entity_type, item.id, action, self._clock.now())

    def add(self, **fields):
        item = self.model_cls(id=self._next_id, **fields)
        self._items[item.id] = item
        self._next_id += 1
        self._log("create", item)
        return item

    def get(self, item_id, include_deleted: bool = False):
        item = self._items.get(item_id)
        if item is None or (item.deleted and not include_deleted):
            raise NotFoundError(f"{self.label}不存在：{item_id}")
        return item

    def list(self, include_deleted: bool = False) -> list:
        return [
            self._items[k]
            for k in sorted(self._items)
            if include_deleted or not self._items[k].deleted
        ]

    def update(self, item_id, **changes):
        item = self.get(item_id)
        for field, value in changes.items():
            if field in ("id", "deleted", "deleted_at") or not hasattr(item, field):
                raise ValueError(f"不能修改字段：{field}")
            setattr(item, field, value)
        self._log("update", item)
        return item

    def delete(self, item_id) -> None:
        item = self.get(item_id)
        item.deleted = True
        item.deleted_at = self._clock.now()
        self._log("delete", item)

    def restore(self, item_id):
        item = self._items.get(item_id)
        if item is None or not item.deleted:
            raise NotFoundError(f"{self.label}不存在：{item_id}")
        item.deleted = False
        item.deleted_at = None
        self._log("restore", item)
        return item
