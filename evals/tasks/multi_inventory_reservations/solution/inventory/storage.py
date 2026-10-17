import json
from pathlib import Path

from .models import Item


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.items: dict[str, Item] = {}
        self.reservations: dict[str, dict[str, int]] = {}
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.items = {d["id"]: Item.from_dict(d) for d in data.get("items", [])}
            self.reservations = data.get("reservations", {})

    def save(self):
        data = {"items": [i.to_dict() for i in self.items.values()], "reservations": self.reservations}
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
