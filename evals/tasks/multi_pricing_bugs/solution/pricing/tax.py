from decimal import ROUND_HALF_UP, Decimal

RATES = {"cn": "0.06", "us": "0.08", "hk": "0"}


def tax_for(amount, region):
    rate = Decimal(RATES[region])
    return (Decimal(amount) * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
