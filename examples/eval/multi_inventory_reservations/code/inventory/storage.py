import json
from pathlib import Path

from .models import Item


class Store:
    """把库存保存在一个 JSON 文件里。"""

    def __init__(self, path):
        self.path = Path(path)
        self.items: dict[str, Item] = {}
        # order_id -> {item_id: 预留数量}
        self.reservations: dict[str, dict[str, int]] = {}
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.items = {d["id"]: Item.from_dict(d) for d in data.get("items", [])}
            # 旧格式的 JSON 可能没有 reservations 字段，默认空。
            for order_id, reserved in data.get("reservations", {}).items():
                self.reservations[order_id] = {
                    item_id: int(qty) for item_id, qty in reserved.items()
                }

    def save(self):
        data = {
            "items": [i.to_dict() for i in self.items.values()],
            "reservations": self.reservations,
        }
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
