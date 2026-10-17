COUPONS = {
    "SAVE10": ("percent", 10),
    "FULL100": ("threshold", (100, 20)),
}


def apply_discount(amount, code):
    if code not in COUPONS:
        raise ValueError(f"无效的优惠码：{code}")
    kind, value = COUPONS[code]
    if kind == "percent":
        return amount * (1 - value / 100)
    if kind == "threshold":
        threshold, off = value
        if amount >= threshold:
            return amount - off
    return amount
