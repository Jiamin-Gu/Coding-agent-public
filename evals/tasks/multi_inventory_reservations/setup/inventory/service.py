from .models import Item
from .storage import Store


class InventoryError(Exception):
    pass


class Inventory:
    def __init__(self, store: Store):
        self.store = store

    def add_item(self, item_id, name, on_hand=0, reorder_level=0):
        if item_id in self.store.items:
            raise InventoryError(f"商品已存在：{item_id}")
        if on_hand < 0:
            raise ValueError("库存不能为负")
        self.store.items[item_id] = Item(item_id, name, on_hand, reorder_level)
        self.store.save()

    def get(self, item_id) -> Item:
        try:
            return self.store.items[item_id]
        except KeyError:
            raise InventoryError(f"商品不存在：{item_id}")

    def receive(self, item_id, qty):
        """入库。"""
        if qty <= 0:
            raise ValueError("数量必须为正")
        self.get(item_id).on_hand += qty
        self.store.save()

    def ship(self, item_id, qty):
        """直接出库。"""
        if qty <= 0:
            raise ValueError("数量必须为正")
        item = self.get(item_id)
        if item.on_hand < qty:
            raise InventoryError(f"库存不足：{item_id}")
        item.on_hand -= qty
        self.store.save()
