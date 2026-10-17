def low_stock(inventory):
    """需要补货的商品 id（可用库存 <= 补货线），按 id 排序。"""
    return sorted(
        i.id
        for i in inventory.store.items.values()
        if inventory.available(i.id) <= i.reorder_level
    )
