from dataclasses import asdict, dataclass


@dataclass
class Item:
    id: str
    name: str
    on_hand: int = 0        # 实际库存
    reorder_level: int = 0  # 补货线

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**d)
