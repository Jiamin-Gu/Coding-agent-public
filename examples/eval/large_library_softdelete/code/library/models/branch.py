from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class Branch:
    """分馆。"""

    id: int
    name: str
    city: str
    deleted: bool = False
    deleted_at: Optional[str] = None

    def to_dict(self):
        return asdict(self)
