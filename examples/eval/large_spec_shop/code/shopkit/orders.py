"""订单流程。"""

import copy
from decimal import Decimal

from .errors import NotFoundError, StateError, StockError, ValidationError
from .money import format_money, parse_money
from ._util import normalize_coupon_code

_DRAFT = "draft"
_PLACED = "placed"
_PAID = "paid"
_SHIPPED = "shipped"
_DELIVERED = "delivered"
_CANCELLED = "cancelled"

STATUSES = (_DRAFT, _PLACED, _PAID, _SHIPPED, _DELIVERED, _CANCELLED)
_CANCELLABLE = (_DRAFT, _PLACED, _PAID)


class OrderMixin:
    """订单相关方法。"""

    def create_order(self, customer, items=None, coupon=None):
        if not isinstance(customer, str):
            raise ValidationError("customer 必须是字符串")
        clean_customer = customer.strip()
        if not clean_customer:
            raise ValidationError("customer 不能为空")

        raw_items = [] if items is None else items
        merged = self._normalize_items(raw_items, allow_empty=True)

        clean_coupon = None
        if coupon is not None:
            if not isinstance(coupon, str):
                raise ValidationError("优惠券代码必须是字符串或 None")
            clean_coupon = normalize_coupon_code(coupon)

        for item in merged:
            product = self.products.get(item["sku"])
            if product is None:
                raise NotFoundError("商品不存在: {!r}".format(item["sku"]))
            if not product["active"]:
                raise ValidationError("商品已下架: {!r}".format(item["sku"]))

        order_id = self._next_order_id()
        order = {
            "id": order_id,
            "customer": clean_customer,
            "status": _DRAFT,
            "items": [{"sku": item["sku"], "qty": item["qty"]} for item in merged],
            "coupon": clean_coupon,
            "pricing": None,
            "paid": None,
            "refund": None,
            "cancel_reason": None,
            "events": [{"at": self._event_time(), "status": _DRAFT}],
        }
        self.orders[order_id] = order
        return order_id

    def add_item(self, order_id, sku, qty):
        if isinstance(qty, bool) or not isinstance(qty, int) or qty < 1:
            raise ValidationError("qty 必须是 >= 1 的 int")
        if not isinstance(sku, str):
            raise ValidationError("sku 必须是字符串")

        order = self._get_order(order_id)
        product = self.products.get(sku)
        if product is None:
            raise NotFoundError("商品不存在: {!r}".format(sku))
        if order["status"] != _DRAFT:
            raise StateError("订单当前状态不允许添加商品")
        if not product["active"]:
            raise ValidationError("商品已下架: {!r}".format(sku))

        for item in order["items"]:
            if item["sku"] == sku:
                item["qty"] += qty
                break
        else:
            order["items"].append({"sku": sku, "qty": qty})
        return self.get_order(order_id)

    def remove_item(self, order_id, sku):
        order = self._get_order(order_id)
        target = None
        for item in order["items"]:
            if item["sku"] == sku:
                target = item
                break
        if target is None:
            raise NotFoundError("订单中没有这个商品: {!r}".format(sku))
        if order["status"] != _DRAFT:
            raise StateError("订单当前状态不允许删除商品")

        order["items"].remove(target)
        return self.get_order(order_id)

    def set_coupon(self, order_id, coupon):
        if coupon is not None and not isinstance(coupon, str):
            raise ValidationError("优惠券代码必须是字符串或 None")
        order = self._get_order(order_id)
        if order["status"] != _DRAFT:
            raise StateError("订单当前状态不允许修改优惠券")
        order["coupon"] = None if coupon is None else normalize_coupon_code(coupon)
        return self.get_order(order_id)

    def place_order(self, order_id):
        order = self._get_order(order_id)
        if order["status"] != _DRAFT:
            raise StateError("订单当前状态不允许下单")
        if not order["items"]:
            raise ValidationError("订单里没有商品")

        merged = [{"sku": item["sku"], "qty": item["qty"]} for item in order["items"]]
        pricing = self._compute_pricing(merged, order["coupon"])

        for item in order["items"]:
            record = self.stock_levels[item["sku"]]
            available = record["on_hand"] - record["reserved"]
            if item["qty"] > available:
                raise StockError("可用库存不足: {!r}".format(item["sku"]))

        for item in order["items"]:
            self.stock_levels[item["sku"]]["reserved"] += item["qty"]

        if order["coupon"] is not None:
            self.coupons[order["coupon"]]["used_by"] = order_id

        order["pricing"] = pricing
        order["status"] = _PLACED
        order["events"].append({"at": self._event_time(), "status": _PLACED})
        return self.get_order(order_id)

    def pay(self, order_id, amount):
        clean_amount = parse_money(amount)
        order = self._get_order(order_id)
        if order["status"] != _PLACED:
            raise StateError("订单当前状态不允许付款")
        if clean_amount != Decimal(order["pricing"]["total"]):
            raise ValidationError("付款金额与应付总额不一致")

        order["paid"] = clean_amount
        order["status"] = _PAID
        order["events"].append({"at": self._event_time(), "status": _PAID})
        return self.get_order(order_id)

    def ship(self, order_id):
        order = self._get_order(order_id)
        if order["status"] != _PAID:
            raise StateError("订单当前状态不允许发货")

        for item in order["items"]:
            sku = item["sku"]
            qty = item["qty"]
            self.stock_levels[sku]["on_hand"] -= qty
            self.stock_levels[sku]["reserved"] -= qty
            self._append_stock_log(sku, -qty, "ship {}".format(order_id))

        order["status"] = _SHIPPED
        order["events"].append({"at": self._event_time(), "status": _SHIPPED})
        return self.get_order(order_id)

    def deliver(self, order_id):
        order = self._get_order(order_id)
        if order["status"] != _SHIPPED:
            raise StateError("订单当前状态不允许送达")
        order["status"] = _DELIVERED
        order["events"].append({"at": self._event_time(), "status": _DELIVERED})
        return self.get_order(order_id)

    def cancel(self, order_id, reason):
        if not isinstance(reason, str):
            raise ValidationError("取消原因必须是字符串")
        clean_reason = reason.strip()
        if not clean_reason:
            raise ValidationError("取消原因不能为空")

        order = self._get_order(order_id)
        if order["status"] not in _CANCELLABLE:
            raise StateError("订单当前状态不允许取消")

        if order["status"] in (_PLACED, _PAID):
            for item in order["items"]:
                self.stock_levels[item["sku"]]["reserved"] -= item["qty"]
            if order["coupon"] is not None:
                coupon = self.coupons.get(order["coupon"])
                if coupon is not None and coupon["used_by"] == order_id:
                    coupon["used_by"] = None

        if order["status"] == _PAID:
            order["refund"] = order["paid"]

        order["cancel_reason"] = clean_reason
        order["status"] = _CANCELLED
        order["events"].append({"at": self._event_time(), "status": _CANCELLED})
        return self.get_order(order_id)

    def get_order(self, order_id):
        order = self._get_order(order_id)
        return self._order_view(order)

    def list_orders(self, status=None, customer=None):
        if status is not None and status not in STATUSES:
            raise ValidationError("非法订单状态: {!r}".format(status))
        clean_customer = None
        if customer is not None:
            if not isinstance(customer, str):
                raise ValidationError("customer 必须是字符串")
            clean_customer = customer.strip()

        result = []
        for order_id in sorted(self.orders):
            order = self.orders[order_id]
            if status is not None and order["status"] != status:
                continue
            if clean_customer is not None and order["customer"] != clean_customer:
                continue
            result.append(self._order_view(order))
        return result

    # --- 内部辅助 -----------------------------------------------------
    def _get_order(self, order_id):
        order = self.orders.get(order_id)
        if order is None:
            raise NotFoundError("订单不存在: {!r}".format(order_id))
        return order

    def _next_order_id(self):
        order_id = "O{:04d}".format(self.next_order_num)
        self.next_order_num += 1
        return order_id

    def _order_view(self, order):
        paid = order["paid"]
        refund = order["refund"]
        return {
            "id": order["id"],
            "customer": order["customer"],
            "status": order["status"],
            "items": [dict(item) for item in order["items"]],
            "coupon": order["coupon"],
            "pricing": copy.deepcopy(order["pricing"]),
            "paid": None if paid is None else format_money(paid),
            "refund": None if refund is None else format_money(refund),
            "cancel_reason": order["cancel_reason"],
            "events": [dict(event) for event in order["events"]],
        }
