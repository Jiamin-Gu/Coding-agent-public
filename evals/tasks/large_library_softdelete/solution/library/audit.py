from dataclasses import dataclass


@dataclass
class AuditEntry:
    entity_type: str
    entity_id: int
    action: str
    at: str


class AuditLog:
    def __init__(self, clock):
        self._clock = clock
        self._entries: list[AuditEntry] = []

    def record(self, entity_type, entity_id, action):
        self._entries.append(AuditEntry(entity_type, entity_id, action, self._clock.now()))

    def entries(self, entity_type=None, entity_id=None, action=None):
        return [e for e in self._entries
                if (entity_type is None or e.entity_type == entity_type)
                and (entity_id is None or e.entity_id == entity_id)
                and (action is None or e.action == action)]
