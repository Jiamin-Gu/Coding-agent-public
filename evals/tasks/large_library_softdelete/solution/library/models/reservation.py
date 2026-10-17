from dataclasses import asdict, dataclass


@dataclass
class Reservation:
    """预约。"""

    id: int
    book_id: int
    member_id: int
    deleted: bool = False
    deleted_at: str | None = None

    def to_dict(self):
        return asdict(self)
