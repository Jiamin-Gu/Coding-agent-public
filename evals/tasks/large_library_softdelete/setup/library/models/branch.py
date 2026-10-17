from dataclasses import asdict, dataclass


@dataclass
class Branch:
    """分馆。"""

    id: int
    name: str
    city: str

    def to_dict(self):
        return asdict(self)
