import copy
import json
import os
import re
import tempfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from .errors import CouponError, NotFoundError, StateError, StockError, ValidationError
from .money import format_money, parse_money, round_money

SKU_RE = re.compile(r"[A-Z0-9-]{1,20}")
CODE_RE = re.compile(r"[A-Z0-9]{3,16}")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
STATUSES = ("draft", "placed", "paid", "shipped", "delivered", "cancelled")
ZERO = Decimal("0.00")


def _int(value, name, minimum, maximum=None):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum or (maximum is not None and value > maximum):
        raise ValidationError(f"invalid {name}: {value!r}")
    return value


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"invalid {name}: {value!r}")
    return value.strip()


def _category(value):
    return _text(value, "category").lower()


def _date(value, name):
    if not isinstance(value, str) or not DATE_RE.fullmatch(value):
        raise ValidationError(f"invalid {name}: {value!r}")
    try:
        date.fromisoformat(value)
    except ValueError:
        raise ValidationError(f"invalid {name}: {value!r}") from None
    return value


def _code(value):
    if not isinstance(value, str):
        raise ValidationError(f"invalid coupon code: {value!r}")
    return value.strip().upper()


def _items(items, allow_empty=False):
    """校验并合并购物清单，返回 [[sku, qty], ...]（按第一次出现的顺序）。"""
    if not isinstance(items, list) or (not items and not allow_empty):
        raise ValidationError("items must be a non-empty list")
    merged: dict[str, int] = {}
    for it in items:
        if not isinstance(it, dict) or "sku" not in it or "qty" not in it or not isinstance(it["sku"], str):
            raise ValidationError(f"invalid item: {it!r}")
        qty = _int(it["qty"], "qty", 1)
        merged[it["sku"]] = merged.get(it["sku"], 0) + qty
    return [[s, q] for s, q in merged.items()]


class Shop:
    def __init__(self, clock=None):
        self._clock = clock or datetime.now
        self._products: dict[str, dict] = {}
        self._stock: dict[str, dict] = {}
        self._log: dict[str, list] = {}
        self._tiers: dict[str, dict[int, Decimal]] = {}
        self._discounts: dict[str, int] = {}
        self._tax: dict[str, Decimal] = {}
        self._coupons: dict[str, dict] = {}
        self._orders: dict[str, dict] = {}
        self._next = 1

    def _now(self) -> str:
        return self._clock().isoformat(timespec="seconds")

    # ---------------------------------------------------------------- 商品

    def _product(self, sku) -> dict:
        if not isinstance(sku, str) or sku not in self._products:
            raise NotFoundError(f"no product {sku!r}")
        return self._products[sku]

    def _product_view(self, sku) -> dict:
        p = self._products[sku]
        return {"sku": sku, "name": p["name"], "price": format_money(p["price"]), "category": p["category"],
                "active": p["active"]}

    def _positive_price(self, value) -> Decimal:
        price = parse_money(value)
        if price <= 0:
            raise ValidationError("price must be > 0")
        return price

    def add_product(self, sku, name, price, category, active=True) -> dict:
        if not isinstance(sku, str) or not SKU_RE.fullmatch(sku):
            raise ValidationError(f"invalid sku: {sku!r}")
        name = _text(name, "name")
        price = self._positive_price(price)
        category = _category(category)
        if not isinstance(active, bool):
            raise ValidationError("active must be bool")
        if sku in self._products:
            raise ValidationError(f"duplicate sku {sku}")
        self._products[sku] = {"name": name, "price": price, "category": category, "active": active}
        self._stock[sku] = {"on_hand": 0, "reserved": 0, "reorder_level": 0}
        self._log[sku] = []
        return self._product_view(sku)

    def get_product(self, sku) -> dict:
        self._product(sku)
        return self._product_view(sku)

    def update_price(self, sku, price) -> dict:
        price = self._positive_price(price)
        self._product(sku)["price"] = price
        return self._product_view(sku)

    def set_active(self, sku, active) -> dict:
        if not isinstance(active, bool):
            raise ValidationError("active must be bool")
        self._product(sku)["active"] = active
        return self._product_view(sku)

    def list_products(self, category=None, active_only=False) -> list[dict]:
        cat = _category(category) if category is not None else None
        return [self._product_view(s) for s in sorted(self._products)
                if (cat is None or self._products[s]["category"] == cat)
                and (not active_only or self._products[s]["active"])]

    # ---------------------------------------------------------------- 库存

    def _stock_view(self, sku) -> dict:
        s = self._stock[sku]
        return {"on_hand": s["on_hand"], "reserved": s["reserved"], "available": s["on_hand"] - s["reserved"]}

    def receive(self, sku, qty) -> dict:
        qty = _int(qty, "qty", 1)
        self._product(sku)
        self._stock[sku]["on_hand"] += qty
        self._log[sku].append({"at": self._now(), "change": qty, "reason": "receive"})
        return self._stock_view(sku)

    def adjust(self, sku, delta, reason) -> dict:
        if isinstance(delta, bool) or not isinstance(delta, int) or delta == 0:
            raise ValidationError("delta must be a non-zero int")
        reason = _text(reason, "reason")
        self._product(sku)
        s = self._stock[sku]
        if s["on_hand"] + delta < s["reserved"]:
            raise StockError("on_hand would drop below reserved")
        s["on_hand"] += delta
        self._log[sku].append({"at": self._now(), "change": delta, "reason": reason})
        return self._stock_view(sku)

    def stock(self, sku) -> dict:
        self._product(sku)
        return self._stock_view(sku)

    def set_reorder_level(self, sku, level) -> dict:
        level = _int(level, "level", 0)
        self._product(sku)
        self._stock[sku]["reorder_level"] = level
        return self._stock_view(sku)

    def low_stock(self) -> list[dict]:
        out = []
        for sku in sorted(self._stock):
            s = self._stock[sku]
            available = s["on_hand"] - s["reserved"]
            if s["reorder_level"] > 0 and available <= s["reorder_level"]:
                out.append({"sku": sku, "available": available, "reorder_level": s["reorder_level"]})
        return out

    def stock_log(self, sku) -> list[dict]:
        self._product(sku)
        return [dict(e) for e in self._log[sku]]

    # ---------------------------------------------------------------- 定价规则

    def set_tier_price(self, sku, min_qty, unit_price):
        min_qty = _int(min_qty, "min_qty", 2)
        price = self._positive_price(unit_price)
        self._product(sku)
        self._tiers.setdefault(sku, {})[min_qty] = price

    def clear_tier_prices(self, sku):
        self._product(sku)
        self._tiers.pop(sku, None)

    def set_category_discount(self, category, percent):
        category = _category(category)
        percent = _int(percent, "percent", 0, 90)
        if percent:
            self._discounts[category] = percent
        else:
            self._discounts.pop(category, None)

    def set_tax_rate(self, category, rate):
        category = _category(category)
        rate = parse_money(rate)
        if rate > 30:
            raise ValidationError("tax rate must be <= 30")
        self._tax[category] = rate

    # ---------------------------------------------------------------- 优惠券

    def add_coupon(self, code, kind, value, min_subtotal="0", expires=None) -> dict:
        code = _code(code)
        if not CODE_RE.fullmatch(code):
            raise ValidationError(f"invalid coupon code {code!r}")
        if kind == "fixed":
            value = self._positive_price(value)
        elif kind == "percent":
            value = _int(value, "percent", 1, 100)
        else:
            raise ValidationError(f"invalid coupon kind {kind!r}")
        min_subtotal = parse_money(min_subtotal)
        if expires is not None:
            expires = _date(expires, "expires")
        if code in self._coupons:
            raise ValidationError(f"duplicate coupon {code}")
        self._coupons[code] = {"kind": kind, "value": value, "min_subtotal": min_subtotal,
                               "expires": expires, "used_by": None}
        return self.get_coupon(code)

    def get_coupon(self, code) -> dict:
        code = _code(code)
        if code not in self._coupons:
            raise NotFoundError(f"no coupon {code}")
        c = self._coupons[code]
        value = format_money(c["value"]) if c["kind"] == "fixed" else c["value"]
        return {"code": code, "kind": c["kind"], "value": value, "min_subtotal": format_money(c["min_subtotal"]),
                "expires": c["expires"], "used_by": c["used_by"]}

    def _coupon_discount(self, code, subtotal: Decimal) -> Decimal:
        c = self._coupons.get(code)
        if c is None:
            raise CouponError(f"no coupon {code}")
        if c["used_by"] is not None:
            raise CouponError(f"coupon {code} already used")
        if c["expires"] is not None and self._clock().date() > date.fromisoformat(c["expires"]):
            raise CouponError(f"coupon {code} expired")
        if subtotal < c["min_subtotal"]:
            raise CouponError(f"coupon {code} needs subtotal >= {c['min_subtotal']}")
        if c["kind"] == "fixed":
            return min(c["value"], subtotal)
        return round_money(subtotal * c["value"] / 100)

    # ---------------------------------------------------------------- 报价

    def _check_items_exist(self, merged):
        for sku, _ in merged:
            p = self._product(sku)
            if not p["active"]:
                raise ValidationError(f"product {sku} is inactive")

    def _price(self, merged, coupon) -> dict:
        lines = []
        for sku, qty in merged:
            p = self._products[sku]
            unit = p["price"]
            tiers = self._tiers.get(sku, {})
            eligible = [m for m in tiers if qty >= m]
            if eligible:
                unit = tiers[max(eligible)]
            line_total = unit * qty
            discount = round_money(line_total * self._discounts.get(p["category"], 0) / 100)
            lines.append({"sku": sku, "category": p["category"], "qty": qty, "unit_price": unit,
                          "line_total": line_total, "discount": discount, "net": line_total - discount})
        subtotal = sum((ln["net"] for ln in lines), ZERO)
        coupon_discount = self._coupon_discount(coupon, subtotal) if coupon is not None else ZERO
        allocated = ZERO
        for i, ln in enumerate(lines):
            if coupon_discount == 0:
                share = ZERO
            elif i < len(lines) - 1:
                share = round_money(coupon_discount * ln["net"] / subtotal)
            else:
                share = coupon_discount - allocated
            allocated += share
            ln["coupon_share"] = share
            ln["tax"] = round_money((ln["net"] - share) * self._tax.get(ln["category"], ZERO) / 100)
        tax = sum((ln["tax"] for ln in lines), ZERO)
        money_keys = ("unit_price", "line_total", "discount", "net", "coupon_share", "tax")
        return {
            "lines": [{**ln, **{k: format_money(ln[k]) for k in money_keys}} for ln in lines],
            "subtotal": format_money(subtotal),
            "coupon": coupon,
            "coupon_discount": format_money(coupon_discount),
            "tax": format_money(tax),
            "total": format_money(subtotal - coupon_discount + tax),
        }

    def quote(self, items, coupon=None) -> dict:
        merged = _items(items)
        code = _code(coupon) if coupon is not None else None
        self._check_items_exist(merged)
        return self._price(merged, code)

    # ---------------------------------------------------------------- 订单

    def _order(self, order_id) -> dict:
        if not isinstance(order_id, str) or order_id not in self._orders:
            raise NotFoundError(f"no order {order_id!r}")
        return self._orders[order_id]

    def _require(self, order, *statuses):
        if order["status"] not in statuses:
            raise StateError(f"order {order['id']} is {order['status']}")

    def _set_status(self, order, status):
        order["status"] = status
        order["events"].append({"at": self._now(), "status": status})

    def get_order(self, order_id) -> dict:
        o = self._order(order_id)
        return {"id": o["id"], "customer": o["customer"], "status": o["status"],
                "items": [{"sku": s, "qty": q} for s, q in o["items"]], "coupon": o["coupon"],
                "pricing": copy.deepcopy(o["pricing"]), "paid": o["paid"], "refund": o["refund"],
                "cancel_reason": o["cancel_reason"], "events": [dict(e) for e in o["events"]]}

    def create_order(self, customer, items=None, coupon=None) -> str:
        customer = _text(customer, "customer")
        merged = _items(items if items is not None else [], allow_empty=True)
        code = _code(coupon) if coupon is not None else None
        self._check_items_exist(merged)
        order_id = f"O{self._next:04d}"
        self._next += 1
        self._orders[order_id] = {"id": order_id, "customer": customer, "status": "draft", "items": merged,
                                  "coupon": code, "pricing": None, "paid": None, "refund": None,
                                  "cancel_reason": None, "events": []}
        self._set_status(self._orders[order_id], "draft")
        return order_id

    def add_item(self, order_id, sku, qty) -> dict:
        qty = _int(qty, "qty", 1)
        o = self._order(order_id)
        p = self._product(sku)
        self._require(o, "draft")
        if not p["active"]:
            raise ValidationError(f"product {sku} is inactive")
        for line in o["items"]:
            if line[0] == sku:
                line[1] += qty
                break
        else:
            o["items"].append([sku, qty])
        return self.get_order(order_id)

    def remove_item(self, order_id, sku) -> dict:
        o = self._order(order_id)
        if not any(line[0] == sku for line in o["items"]):
            raise NotFoundError(f"{sku!r} not in order")
        self._require(o, "draft")
        o["items"] = [line for line in o["items"] if line[0] != sku]
        return self.get_order(order_id)

    def set_coupon(self, order_id, coupon) -> dict:
        code = _code(coupon) if coupon is not None else None
        o = self._order(order_id)
        self._require(o, "draft")
        o["coupon"] = code
        return self.get_order(order_id)

    def place_order(self, order_id) -> dict:
        o = self._order(order_id)
        self._require(o, "draft")
        if not o["items"]:
            raise ValidationError("order has no items")
        self._check_items_exist(o["items"])
        pricing = self._price(o["items"], o["coupon"])
        for sku, qty in o["items"]:
            s = self._stock[sku]
            if qty > s["on_hand"] - s["reserved"]:
                raise StockError(f"not enough {sku}")
        for sku, qty in o["items"]:
            self._stock[sku]["reserved"] += qty
        if o["coupon"] is not None:
            self._coupons[o["coupon"]]["used_by"] = order_id
        o["pricing"] = pricing
        self._set_status(o, "placed")
        return self.get_order(order_id)

    def pay(self, order_id, amount) -> dict:
        amount = parse_money(amount)
        o = self._order(order_id)
        self._require(o, "placed")
        if amount != Decimal(o["pricing"]["total"]):
            raise ValidationError(f"amount must be {o['pricing']['total']}")
        o["paid"] = format_money(amount)
        self._set_status(o, "paid")
        return self.get_order(order_id)

    def ship(self, order_id) -> dict:
        o = self._order(order_id)
        self._require(o, "paid")
        now = self._now()
        for sku, qty in o["items"]:
            self._stock[sku]["on_hand"] -= qty
            self._stock[sku]["reserved"] -= qty
            self._log[sku].append({"at": now, "change": -qty, "reason": f"ship {order_id}"})
        self._set_status(o, "shipped")
        return self.get_order(order_id)

    def deliver(self, order_id) -> dict:
        o = self._order(order_id)
        self._require(o, "shipped")
        self._set_status(o, "delivered")
        return self.get_order(order_id)

    def cancel(self, order_id, reason) -> dict:
        reason = _text(reason, "reason")
        o = self._order(order_id)
        self._require(o, "draft", "placed", "paid")
        if o["status"] in ("placed", "paid"):
            for sku, qty in o["items"]:
                self._stock[sku]["reserved"] -= qty
            if o["coupon"] is not None:
                self._coupons[o["coupon"]]["used_by"] = None
        if o["status"] == "paid":
            o["refund"] = o["paid"]
        o["cancel_reason"] = reason
        self._set_status(o, "cancelled")
        return self.get_order(order_id)

    def list_orders(self, status=None, customer=None) -> list[dict]:
        if status is not None and status not in STATUSES:
            raise ValidationError(f"invalid status {status!r}")
        who = _text(customer, "customer") if customer is not None else None
        return [self.get_order(i) for i in sorted(self._orders)
                if (status is None or self._orders[i]["status"] == status)
                and (who is None or self._orders[i]["customer"] == who)]

    # ---------------------------------------------------------------- 报表

    def _shipped(self, start=None, end=None):
        for oid in sorted(self._orders):
            o = self._orders[oid]
            if o["status"] not in ("shipped", "delivered"):
                continue
            day = next(e["at"][:10] for e in o["events"] if e["status"] == "shipped")
            if (start is None or day >= start) and (end is None or day <= end):
                yield o

    def sales_report(self, start, end) -> dict:
        start, end = _date(start, "start"), _date(end, "end")
        if start > end:
            raise ValidationError("start is after end")
        orders = list(self._shipped(start, end))
        cats: dict[str, dict] = {}
        units = 0
        for o in orders:
            for ln in o["pricing"]["lines"]:
                units += ln["qty"]
                c = cats.setdefault(ln["category"], {"units": 0, "net": ZERO})
                c["units"] += ln["qty"]
                c["net"] += Decimal(ln["net"])

        def total(key):
            return format_money(sum((Decimal(o["pricing"][key]) for o in orders), ZERO))
        by_category = sorted(cats.items(), key=lambda kv: (-kv[1]["net"], kv[0]))
        return {"orders": len(orders), "units": units, "subtotal": total("subtotal"),
                "coupon_discount": total("coupon_discount"), "tax": total("tax"), "revenue": total("total"),
                "by_category": [{"category": k, "units": v["units"], "net": format_money(v["net"])}
                                for k, v in by_category]}

    def top_products(self, limit=5, start=None, end=None) -> list[dict]:
        limit = _int(limit, "limit", 1)
        start = _date(start, "start") if start is not None else None
        end = _date(end, "end") if end is not None else None
        units: dict[str, int] = {}
        for o in self._shipped(start, end):
            for sku, qty in o["items"]:
                units[sku] = units.get(sku, 0) + qty
        ranked = sorted(units.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
        return [{"sku": s, "units": u} for s, u in ranked]

    def inventory_value(self) -> str:
        return format_money(sum((self._products[s]["price"] * self._stock[s]["on_hand"] for s in self._products), ZERO))

    # ---------------------------------------------------------------- 持久化

    def save(self, path) -> None:
        path = Path(path)
        data = {
            "products": {s: {**p, "price": str(p["price"])} for s, p in self._products.items()},
            "stock": self._stock, "log": self._log,
            "tiers": {s: {str(m): str(v) for m, v in t.items()} for s, t in self._tiers.items()},
            "discounts": self._discounts, "tax": {c: str(r) for c, r in self._tax.items()},
            "coupons": {c: {**v, "value": str(v["value"]) if v["kind"] == "fixed" else v["value"],
                            "min_subtotal": str(v["min_subtotal"])} for c, v in self._coupons.items()},
            "orders": self._orders, "next": self._next,
        }
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)

    @classmethod
    def load(cls, path, clock=None) -> "Shop":
        path = Path(path)
        if not path.is_file():
            raise NotFoundError(f"no file {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        shop = cls(clock)
        shop._products = {s: {**p, "price": Decimal(p["price"])} for s, p in data["products"].items()}
        shop._stock = data["stock"]
        shop._log = data["log"]
        shop._tiers = {s: {int(m): Decimal(v) for m, v in t.items()} for s, t in data["tiers"].items()}
        shop._discounts = data["discounts"]
        shop._tax = {c: Decimal(r) for c, r in data["tax"].items()}
        shop._coupons = {c: {**v, "value": Decimal(v["value"]) if v["kind"] == "fixed" else v["value"],
                             "min_subtotal": Decimal(v["min_subtotal"])} for c, v in data["coupons"].items()}
        shop._orders = data["orders"]
        shop._next = data["next"]
        return shop
