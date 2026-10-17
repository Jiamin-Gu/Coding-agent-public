from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class Fine:
    """罚款。"""

    id: int
    member_id: int
    amount: int
    paid: bool = False
    deleted: bool = False
    deleted_at: Optional[str] = None

    def to_dict(self):
        return asdict(self)
