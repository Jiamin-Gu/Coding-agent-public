from dataclasses import asdict, dataclass


@dataclass
class Loan:
    """借阅记录。"""

    id: int
    book_id: int
    member_id: int
    due: str
    returned: bool = False
    deleted: bool = False
    deleted_at: str | None = None

    def to_dict(self):
        return asdict(self)
