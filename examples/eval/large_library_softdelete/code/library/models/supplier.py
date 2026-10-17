from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class Supplier:
    """供应商。"""

    id: int
    name: str
    contact: str = ""
    deleted: bool = False
    deleted_at: Optional[str] = None

    def to_dict(self):
        return asdict(self)
