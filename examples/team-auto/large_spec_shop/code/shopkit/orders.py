"""Order lifecycle: drafts, items, placement, payment, shipping, cancellation."""

from copy import deepcopy
from decimal import Decimal

from ._util import norm_code, norm_text, now_iso, validate_qty
from .errors import NotFoundError, StateError, StockError, ValidationError
from .money import format_money, parse_money

_STATUSES = ("draft", "placed", "paid", "shipped", "delivered", "cancelled")
_CANCELLABLE = ("draft", "placed", "paid")


class OrdersMixin:
    """Order state machine on top of the shared Shop state."""

    def _require_order(self, oid):
        order = self._orders.get(oid)
        if order is None:
            raise NotFoundError("order not found")
        return order

    def create_order(self, customer, items=None, coupon=None):
        """Create a draft order and return its id."""
        customer_norm = norm_text(customer, "customer")
        if items is None:
            items_norm = []
        else:
            items_norm = self._merge_items(items, allow_empty=True)
        if coupon is None:
            coupon_code = None
        else:
            coupon_code = norm_code(coupon)

        self._order_seq += 1
        oid = f"O{self._order_seq:04d}"
        self._orders[oid] = {
            "id": oid,
            "customer": customer_norm,
            "status": "draft",
            "items": items_norm,
            "coupon": coupon_code,
            "pricing": None,
            "paid": None,
            "refund": None,
            "cancel_reason": None,
            "events": [{"at": now_iso(self._clock), "status": "draft"}],
        }
        return oid

    def get_order(self, oid):
        """Return a deep copy of an order; missing ids raise NotFoundError."""
        return deepcopy(self._require_order(oid))

    def list_orders(self, status=None, customer=None):
        """Return orders sorted by id, optionally filtered by status/customer."""
        if status is not None and status not in _STATUSES:
            raise ValidationError("invalid status")
        if customer is not None:
            if not isinstance(customer, str):
                raise ValidationError("customer must be a string")
            customer_norm = customer.strip()
        else:
            customer_norm = None

        result = []
        for oid in sorted(self._orders):
            order = self._orders[oid]
            if status is not None and order["status"] != status:
                continue
            if customer_norm is not None and order["customer"] != customer_norm:
                continue
            result.append(deepcopy(order))
        return result

    def add_item(self, oid, sku, qty):
        """Add ``qty`` of ``sku`` to a draft order (merging into existing lines)."""
        qty_norm = validate_qty(qty)
        order = self._require_order(oid)
        if order["status"] != "draft":
            raise StateError("order is not a draft")
        product = self._product(sku)
        if not product["active"]:
            raise ValidationError("product is not active")

        for item in order["items"]:
            if item["sku"] == sku:
                item["qty"] += qty_norm
                return self.get_order(oid)
        order["items"].append({"sku": sku, "qty": qty_norm})
        return self.get_order(oid)

    def remove_item(self, oid, sku):
        """Remove ``sku`` from a draft order."""
        order = self._require_order(oid)
        if order["status"] != "draft":
            raise StateError("order is not a draft")
        for index, item in enumerate(order["items"]):
            if item["sku"] == sku:
                del order["items"][index]
                return self.get_order(oid)
        raise NotFoundError("sku is not in the order")

    def set_coupon(self, oid, coupon):
        """Set or clear (``None``) the coupon of a draft order."""
        coupon_code = None if coupon is None else norm_code(coupon)
        order = self._require_order(oid)
        if order["status"] != "draft":
            raise StateError("order is not a draft")
        order["coupon"] = coupon_code
        return self.get_order(oid)

    def place_order(self, oid):
        """Place a draft order, reserving stock and occupying the coupon."""
        order = self._require_order(oid)
        if order["status"] != "draft":
            raise StateError("order is not a draft")
        if not order["items"]:
            raise ValidationError("order has no items")

        pricing = self.quote(order["items"], order["coupon"])

        for item in order["items"]:
            state = self._stock_state(item["sku"])
            available = state["on_hand"] - state["reserved"]
            if item["qty"] > available:
                raise StockError("insufficient stock")

        for item in order["items"]:
            self._stock_state(item["sku"])["reserved"] += item["qty"]
        if order["coupon"] is not None:
            coupon = self._coupons.get(order["coupon"])
            if coupon is not None:
                coupon["used_by"] = oid

        order["pricing"] = pricing
        order["status"] = "placed"
        order["events"].append({"at": now_iso(self._clock), "status": "placed"})
        return self.get_order(oid)

    def pay(self, oid, amount):
        """Record payment for a placed order; amount must equal the total."""
        amount_norm = parse_money(amount)
        order = self._require_order(oid)
        if order["status"] != "placed":
            raise StateError("order is not placed")
        if amount_norm != Decimal(order["pricing"]["total"]):
            raise ValidationError("payment amount does not match the order total")

        order["paid"] = format_money(amount_norm)
        order["status"] = "paid"
        order["events"].append({"at": now_iso(self._clock), "status": "paid"})
        return self.get_order(oid)

    def ship(self, oid):
        """Ship a paid order, moving reserved stock out and logging the change."""
        order = self._require_order(oid)
        if order["status"] != "paid":
            raise StateError("order is not paid")

        at = now_iso(self._clock)
        for item in order["items"]:
            state = self._stock_state(item["sku"])
            state["on_hand"] -= item["qty"]
            state["reserved"] -= item["qty"]
            self._logs[item["sku"]].append(
                {"at": at, "change": -item["qty"], "reason": f"ship {oid}"}
            )
        order["status"] = "shipped"
        order["events"].append({"at": at, "status": "shipped"})
        return self.get_order(oid)

    def deliver(self, oid):
        """Mark a shipped order as delivered."""
        order = self._require_order(oid)
        if order["status"] != "shipped":
            raise StateError("order is not shipped")
        order["status"] = "delivered"
        order["events"].append({"at": now_iso(self._clock), "status": "delivered"})
        return self.get_order(oid)

    def cancel(self, oid, reason):
        """Cancel a draft/placed/paid order, releasing stock and the coupon."""
        reason_norm = norm_text(reason, "reason")
        order = self._require_order(oid)
        if order["status"] not in _CANCELLABLE:
            raise StateError("order cannot be cancelled")

        if order["status"] in ("placed", "paid"):
            for item in order["items"]:
                self._stock_state(item["sku"])["reserved"] -= item["qty"]
        if order["coupon"] is not None:
            coupon = self._coupons.get(order["coupon"])
            if coupon is not None and coupon["used_by"] == oid:
                coupon["used_by"] = None
        if order["status"] == "paid":
            order["refund"] = order["paid"]

        order["cancel_reason"] = reason_norm
        order["status"] = "cancelled"
        order["events"].append({"at": now_iso(self._clock), "status": "cancelled"})
        return self.get_order(oid)
