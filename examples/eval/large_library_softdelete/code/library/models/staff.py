from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class Staff:
    """员工。"""

    id: int
    name: str
    branch_id: int
    role: str = "librarian"
    deleted: bool = False
    deleted_at: Optional[str] = None

    def to_dict(self):
        return asdict(self)
