from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class Member:
    """会员。"""

    id: int
    name: str
    email: str
    level: str = "basic"
    deleted: bool = False
    deleted_at: Optional[str] = None

    def to_dict(self):
        return asdict(self)
