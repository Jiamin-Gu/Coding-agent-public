from dataclasses import asdict, dataclass


@dataclass
class Book:
    """图书。"""

    id: int
    title: str
    author: str
    isbn: str
    branch_id: int
    deleted: bool = False
    deleted_at: str | None = None

    def to_dict(self):
        return asdict(self)
