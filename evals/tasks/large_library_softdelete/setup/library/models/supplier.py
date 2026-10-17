from dataclasses import asdict, dataclass


@dataclass
class Supplier:
    """供应商。"""

    id: int
    name: str
    contact: str = ""

    def to_dict(self):
        return asdict(self)
