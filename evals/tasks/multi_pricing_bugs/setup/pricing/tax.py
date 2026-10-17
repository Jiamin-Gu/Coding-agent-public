from decimal import Decimal

RATES = {"cn": "0.06", "us": "0.08", "hk": "0"}


def tax_for(amount, region):
    """按地区税率计算税额，四舍五入到分。"""
    rate = Decimal(RATES[region])
    return round(float(amount * rate), 2)
