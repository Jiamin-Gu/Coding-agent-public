def low_stock(inventory):
    """需要补货的商品 id（库存 <= 补货线），按 id 排序。"""
    return sorted(i.id for i in inventory.store.items.values() if i.on_hand <= i.reorder_level)
