from dataclasses import dataclass
from typing import Optional


@dataclass
class AuditEntry:
    """一条审计日志。"""

    entity_type: str
    entity_id: int
    action: str
    at: str


class AuditLog:
    """记录通过 Repo 进行的每一次增删改恢复操作。"""

    def __init__(self):
        self._entries: list[AuditEntry] = []

    def record(self, entity_type: str, entity_id: int, action: str, at: str) -> AuditEntry:
        entry = AuditEntry(entity_type=entity_type, entity_id=entity_id, action=action, at=at)
        self._entries.append(entry)
        return entry

    def entries(
        self,
        entity_type: Optional[str] = None,
        entity_id: Optional[int] = None,
        action: Optional[str] = None,
    ) -> list[AuditEntry]:
        """按条件过滤日志，按记录的先后顺序返回。"""
        return [
            e
            for e in self._entries
            if (entity_type is None or e.entity_type == entity_type)
            and (entity_id is None or e.entity_id == entity_id)
            and (action is None or e.action == action)
        ]
