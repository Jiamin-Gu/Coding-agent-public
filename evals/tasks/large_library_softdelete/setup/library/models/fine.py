from dataclasses import asdict, dataclass


@dataclass
class Fine:
    """罚款。"""

    id: int
    member_id: int
    amount: int
    paid: bool = False

    def to_dict(self):
        return asdict(self)
