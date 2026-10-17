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
        """直接出库（只能使用可用库存）。"""
        if qty <= 0:
            raise ValueError("数量必须为正")
        item = self.get(item_id)
        if self.available(item_id) < qty:
            raise InventoryError(f"库存不足：{item_id}")
        item.on_hand -= qty
        self.store.save()

    def reserve(self, order_id, item_id, qty):
        """为订单预留库存。"""
        if qty <= 0:
            raise ValueError("数量必须为正")
        self.get(item_id)
        if self.available(item_id) < qty:
            raise InventoryError(f"可用库存不足：{item_id}")
        reserved = self.store.reservations.setdefault(order_id, {})
        reserved[item_id] = reserved.get(item_id, 0) + qty
        self.store.save()

    def release(self, order_id):
        """取消订单的全部预留。"""
        if order_id not in self.store.reservations:
            raise InventoryError(f"订单不存在：{order_id}")
        del self.store.reservations[order_id]
        self.store.save()

    def fulfill(self, order_id):
        """订单发货：按预留数量扣减实际库存，并删除该订单的预留。"""
        if order_id not in self.store.reservations:
            raise InventoryError(f"订单不存在：{order_id}")
        for item_id, qty in self.store.reservations[order_id].items():
            self.get(item_id).on_hand -= qty
        del self.store.reservations[order_id]
        self.store.save()

    def available(self, item_id) -> int:
        """可用库存 = 实际库存 - 所有订单对该商品的预留之和。"""
        item = self.get(item_id)
        reserved = sum(
            order.get(item_id, 0) for order in self.store.reservations.values()
        )
        return item.on_hand - reserved
