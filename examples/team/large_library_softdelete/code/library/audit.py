from __future__ import annotations

from dataclasses import dataclass

from .clock import Clock


@dataclass
class AuditEntry:
    """一条审计日志：对某个实体的一次操作。"""

    entity_type: str
    entity_id: int
    action: str
    at: str


class AuditLog:
    """记录通过 Repo 进行的 add / update / delete / restore 操作。

    action 取值固定为 'create' / 'update' / 'delete' / 'restore'。
    """

    def __init__(self, clock=None):
        self.clock = clock or Clock()
        self._entries: list[AuditEntry] = []

    def record(self, entity_type, entity_id, action) -> AuditEntry:
        entry = AuditEntry(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            at=self.clock.now(),
        )
        self._entries.append(entry)
        return entry

    def entries(self, entity_type=None, entity_id=None, action=None) -> list[AuditEntry]:
        """按条件过滤，按记录先后顺序返回；多个条件为“与”关系。

        三个参数为 None 表示不过滤，非 None 时精确相等匹配。
        返回新列表，不暴露内部列表。
        """
        result = []
        for entry in self._entries:
            if entity_type is not None and entry.entity_type != entity_type:
                continue
            if entity_id is not None and entry.entity_id != entity_id:
                continue
            if action is not None and entry.action != action:
                continue
            result.append(entry)
        return result
