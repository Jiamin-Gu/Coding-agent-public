import json
from pathlib import Path

from .models import Item


class Store:
    """把库存保存在一个 JSON 文件里。"""

    def __init__(self, path):
        self.path = Path(path)
        self.items: dict[str, Item] = {}
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.items = {d["id"]: Item.from_dict(d) for d in data.get("items", [])}

    def save(self):
        data = {"items": [i.to_dict() for i in self.items.values()]}
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
