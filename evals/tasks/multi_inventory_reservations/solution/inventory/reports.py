def low_stock(inventory):
    return sorted(i.id for i in inventory.store.items.values() if inventory.available(i.id) <= i.reorder_level)
