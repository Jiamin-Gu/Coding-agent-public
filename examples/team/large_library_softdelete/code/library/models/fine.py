from dataclasses import asdict, dataclass


@dataclass
class Fine:
    """罚款。"""

    id: int
    member_id: int
    amount: int
    paid: bool = False
    deleted: bool = False
    deleted_at: str | None = None

    def to_dict(self):
        return asdict(self)
