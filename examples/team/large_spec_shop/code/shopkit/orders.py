"""订单：``OrderMixin``，订单号、状态机、库存预留/释放/扣减、优惠券占用与价格快照。

所有会修改状态的方法都保证原子性：任何校验失败都不留下部分修改。
返回值里的金额一律是 ``format_money`` 的字符串。
"""

import copy
from decimal import Decimal

from shopkit.errors import (
    NotFoundError,
    StateError,
    StockError,
    ValidationError,
)
from shopkit.money import format_money, parse_money

# 合法订单状态
_VALID_STATUSES = ("draft", "placed", "paid", "shipped", "delivered", "cancelled")
# 允许取消的状态
_CANCELLABLE = ("draft", "placed", "paid")


class OrderMixin:
    """订单相关方法，供 :class:`~shopkit.shop.Shop` 混入。"""

    # --- 辅助 -----------------------------------------------------------

    def _get_order(self, order_id) -> dict:
        """返回内部订单 dict（不存在 → NotFoundError）。"""
        if not isinstance(order_id, str):
            raise ValidationError(f"订单号必须是字符串，不能是 {type(order_id).__name__}")
        try:
            return self._orders[order_id]
        except KeyError:
            raise NotFoundError(f"订单不存在：{order_id!r}") from None

    @staticmethod
    def _require_status(order: dict, expected: str) -> None:
        """订单状态不是 expected → StateError。"""
        if order["status"] != expected:
            raise StateError(
                f"订单 {order['id']} 当前状态为 {order['status']!r}，不允许该操作"
            )

    def _merge_order_items(self, items):
        """校验 items 结构并合并重复 sku（允许空列表），保留首次出现的位置。"""
        if not isinstance(items, list):
            raise ValidationError(f"items 必须是列表，不能是 {type(items).__name__}")

        order = []
        quantities = {}
        for item in items:
            if not isinstance(item, dict) or set(item.keys()) != {"sku", "qty"}:
                raise ValidationError(f"清单元素必须是 {{'sku','qty'}}：{item!r}")
            sku = item["sku"]
            if not isinstance(sku, str):
                raise ValidationError(f"sku 必须是字符串，不能是 {type(sku).__name__}")
            self._validate_qty(item["qty"])
            if sku not in quantities:
                order.append(sku)
                quantities[sku] = 0
            quantities[sku] += item["qty"]
        return order, quantities

    def _resolve_order_items(self, sku_order, quantities) -> list:
        """把合并后的 sku 解析成订单行，校验存在与上架。"""
        resolved = []
        for sku in sku_order:
            product = self._get_product(sku)
            if not product["active"]:
                raise ValidationError(f"商品已下架：{sku!r}")
            resolved.append({"sku": sku, "qty": quantities[sku]})
        return resolved

    # --- 创建与草稿编辑 -------------------------------------------------

    def create_order(self, customer, items=None, coupon=None) -> str:
        """创建草稿订单，返回订单号。"""
        if not isinstance(customer, str):
            raise ValidationError(f"customer 必须是字符串，不能是 {type(customer).__name__}")
        clean_customer = customer.strip()
        if clean_customer == "":
            raise ValidationError("customer 不能为空")

        normalized_coupon = None
        if coupon is not None:
            if not isinstance(coupon, str):
                raise ValidationError(f"优惠券代码必须是字符串，不能是 {type(coupon).__name__}")
            normalized_coupon = self._normalize_code(coupon)

        resolved_items = []
        if items is not None:
            sku_order, quantities = self._merge_order_items(items)
            resolved_items = self._resolve_order_items(sku_order, quantities)

        # 先取时间戳，保证 clock 抛异常时不会消耗订单号
        now = self._now()

        order_id = f"O{self._next_no:04d}"
        self._next_no += 1

        self._orders[order_id] = {
            "id": order_id,
            "customer": clean_customer,
            "status": "draft",
            "items": resolved_items,
            "coupon": normalized_coupon,
            "pricing": None,
            "paid": None,
            "refund": None,
            "cancel_reason": None,
            "events": [{"at": now, "status": "draft"}],
        }
        return order_id

    def add_item(self, order_id, sku, qty) -> dict:
        """向草稿订单加入商品，已有则累加数量。"""
        self._validate_qty(qty)
        if not isinstance(sku, str):
            raise ValidationError(f"sku 必须是字符串，不能是 {type(sku).__name__}")

        order = self._get_order(order_id)
        self._require_status(order, "draft")

        product = self._get_product(sku)
        if not product["active"]:
            raise ValidationError(f"商品已下架：{sku!r}")

        for item in order["items"]:
            if item["sku"] == sku:
                item["qty"] += qty
                break
        else:
            order["items"].append({"sku": sku, "qty": qty})
        return self.get_order(order_id)

    def remove_item(self, order_id, sku) -> dict:
        """从草稿订单移除商品；订单里没有该 sku → NotFoundError。"""
        if not isinstance(sku, str):
            raise ValidationError(f"sku 必须是字符串，不能是 {type(sku).__name__}")

        order = self._get_order(order_id)
        self._require_status(order, "draft")

        for index, item in enumerate(order["items"]):
            if item["sku"] == sku:
                order["items"].pop(index)
                return self.get_order(order_id)
        raise NotFoundError(f"订单 {order_id} 中没有商品：{sku!r}")

    def set_coupon(self, order_id, coupon) -> dict:
        """设置/清除草稿订单的优惠券（只保存规范化代码，None 表示清除）。"""
        if coupon is not None and not isinstance(coupon, str):
            raise ValidationError(f"优惠券代码必须是字符串，不能是 {type(coupon).__name__}")

        order = self._get_order(order_id)
        self._require_status(order, "draft")

        order["coupon"] = self._normalize_code(coupon) if coupon is not None else None
        return self.get_order(order_id)

    # --- 状态流转 -------------------------------------------------------

    def place_order(self, order_id) -> dict:
        """下单：报价、检查库存、预留库存、占用优惠券并保存价格快照。"""
        order = self._get_order(order_id)
        self._require_status(order, "draft")

        if not order["items"]:
            raise ValidationError("订单里没有商品")

        # 先报价（含优惠券可用性与下架检查），失败则无任何副作用
        pricing = self.quote(order["items"], order["coupon"])

        # 逐行检查可用库存，全部通过后才修改状态
        for item in order["items"]:
            if item["qty"] > self._available(item["sku"]):
                raise StockError(
                    f"商品 {item['sku']!r} 可用库存不足：需要 {item['qty']}"
                )

        # 先取时间戳，再执行任何写操作
        now = self._now()

        for item in order["items"]:
            self._reserve(item["sku"], item["qty"])

        if order["coupon"] is not None:
            self._coupons[order["coupon"]]["used_by"] = order_id

        order["pricing"] = pricing
        order["status"] = "placed"
        order["events"].append({"at": now, "status": "placed"})
        return self.get_order(order_id)

    def pay(self, order_id, amount) -> dict:
        """付款：金额必须正好等于报价总额。"""
        clean_amount = parse_money(amount)

        order = self._get_order(order_id)
        self._require_status(order, "placed")

        if clean_amount != Decimal(order["pricing"]["total"]):
            raise ValidationError(
                f"付款金额 {format_money(clean_amount)} 与订单总额 "
                f"{order['pricing']['total']} 不一致"
            )

        # 先取时间戳，再执行任何写操作
        now = self._now()

        order["paid"] = format_money(clean_amount)
        order["status"] = "paid"
        order["events"].append({"at": now, "status": "paid"})
        return self.get_order(order_id)

    def ship(self, order_id) -> dict:
        """发货：逐行扣减库存（on_hand/reserved）并记流水。"""
        order = self._get_order(order_id)
        self._require_status(order, "paid")

        # 防御性检查，保证原子性
        for item in order["items"]:
            if self._stock[item["sku"]]["on_hand"] < item["qty"]:
                raise StockError(
                    f"商品 {item['sku']!r} 在手数量不足：需要 {item['qty']}"
                )

        # 先取时间戳，再执行任何写操作；所有流水与事件统一用这个时间
        now = self._now()

        for item in order["items"]:
            sku = item["sku"]
            self._consume(sku, item["qty"])
            self._stock[sku]["log"].append(
                {"at": now, "change": -item["qty"], "reason": f"ship {order_id}"}
            )

        order["status"] = "shipped"
        order["events"].append({"at": now, "status": "shipped"})
        return self.get_order(order_id)

    def deliver(self, order_id) -> dict:
        """送达：只能是已发货状态。"""
        order = self._get_order(order_id)
        self._require_status(order, "shipped")

        now = self._now()
        order["status"] = "delivered"
        order["events"].append({"at": now, "status": "delivered"})
        return self.get_order(order_id)

    def cancel(self, order_id, reason) -> dict:
        """取消订单：释放预留、释放优惠券，已付款则记录退款。"""
        if not isinstance(reason, str):
            raise ValidationError(f"reason 必须是字符串，不能是 {type(reason).__name__}")
        clean_reason = reason.strip()
        if clean_reason == "":
            raise ValidationError("reason 不能为空")

        order = self._get_order(order_id)
        if order["status"] not in _CANCELLABLE:
            raise StateError(
                f"订单 {order['id']} 当前状态为 {order['status']!r}，不允许取消"
            )

        # 先取时间戳，再执行任何写操作
        now = self._now()

        if order["status"] in ("placed", "paid"):
            for item in order["items"]:
                self._release(item["sku"], item["qty"])

            coupon_code = order["coupon"]
            if coupon_code is not None:
                coupon = self._coupons.get(coupon_code)
                if coupon is not None and coupon["used_by"] == order_id:
                    coupon["used_by"] = None

        if order["status"] == "paid":
            order["refund"] = order["paid"]

        order["cancel_reason"] = clean_reason
        order["status"] = "cancelled"
        order["events"].append({"at": now, "status": "cancelled"})
        return self.get_order(order_id)

    # --- 查询 -----------------------------------------------------------

    def get_order(self, order_id) -> dict:
        """返回订单副本（外部修改不影响内部状态）。"""
        return copy.deepcopy(self._get_order(order_id))

    def list_orders(self, status=None, customer=None) -> list:
        """按订单号升序列出订单，可按状态、客户过滤。"""
        if status is not None and status not in _VALID_STATUSES:
            raise ValidationError(f"订单状态不合法：{status!r}")

        clean_customer = None
        if customer is not None:
            if not isinstance(customer, str):
                raise ValidationError(
                    f"customer 必须是字符串，不能是 {type(customer).__name__}"
                )
            clean_customer = customer.strip()

        result = []
        for order_id in sorted(self._orders):
            order = self._orders[order_id]
            if status is not None and order["status"] != status:
                continue
            if clean_customer is not None and order["customer"] != clean_customer:
                continue
            result.append(copy.deepcopy(order))
        return result

