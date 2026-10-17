from dataclasses import asdict, dataclass


@dataclass
class Branch:
    """分馆。"""

    id: int
    name: str
    city: str
    deleted: bool = False
    deleted_at: str | None = None

    def to_dict(self):
        return asdict(self)
