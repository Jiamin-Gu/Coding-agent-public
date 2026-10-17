from dataclasses import asdict, dataclass


@dataclass
class Member:
    """会员。"""

    id: int
    name: str
    email: str
    level: str = "basic"

    def to_dict(self):
        return asdict(self)
