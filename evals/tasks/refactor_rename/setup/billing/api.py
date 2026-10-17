from . import core


def quote(items, region):
    tax = {"cn": 0.06, "us": 0.08}.get(region, 0.0)
    return {"region": region, "total": core.calc_total(items, tax_rate=tax)}
