def compute_total(items, tax_rate=0.0):
    """items 是 (单价, 数量) 的列表，返回含税总价。"""
    subtotal = sum(price * qty for price, qty in items)
    return round(subtotal * (1 + tax_rate), 2)
