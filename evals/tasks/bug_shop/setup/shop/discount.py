COUPONS = {
    "SAVE10": ("percent", 10),            # 打九折
    "FULL100": ("threshold", (100, 20)),  # 满 100 减 20
}


def apply_discount(amount, code):
    kind, value = COUPONS[code]
    if kind == "percent":
        return amount * (1 - value)
    if kind == "threshold":
        threshold, off = value
        if amount > threshold:
            return amount - off
    return amount
