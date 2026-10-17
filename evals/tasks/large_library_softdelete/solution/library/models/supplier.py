from dataclasses import asdict, dataclass


@dataclass
class Supplier:
    """供应商。"""

    id: int
    name: str
    contact: str = ""
    deleted: bool = False
    deleted_at: str | None = None

    def to_dict(self):
        return asdict(self)
