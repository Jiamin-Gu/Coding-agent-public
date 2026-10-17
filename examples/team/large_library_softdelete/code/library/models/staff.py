from dataclasses import asdict, dataclass


@dataclass
class Staff:
    """员工。"""

    id: int
    name: str
    branch_id: int
    role: str = "librarian"
    deleted: bool = False
    deleted_at: str | None = None

    def to_dict(self):
        return asdict(self)
