from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class Book:
    """图书。"""

    id: int
    title: str
    author: str
    isbn: str
    branch_id: int
    deleted: bool = False
    deleted_at: Optional[str] = None

    def to_dict(self):
        return asdict(self)
