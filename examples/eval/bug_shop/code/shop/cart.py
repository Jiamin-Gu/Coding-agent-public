from .discount import apply_discount


class Cart:
    def __init__(self):
        self.items = []  # (名称, 单价, 数量)

    def add(self, name, price, qty=1):
        self.items.append((name, price, qty))

    def subtotal(self):
        return sum(price * qty for name, price, qty in self.items)

    def total(self, coupon=None):
        amount = self.subtotal()
        if coupon:
            amount = apply_discount(amount, coupon)
        return round(amount, 2)
