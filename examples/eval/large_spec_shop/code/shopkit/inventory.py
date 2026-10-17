"""库存管理。"""

from .errors import NotFoundError, StockError, ValidationError


def _validate_qty(qty):
    if isinstance(qty, bool) or not isinstance(qty, int):
        raise ValidationError("数量必须是 int: {!r}".format(qty))
    if qty < 1:
        raise ValidationError("数量必须大于等于 1: {!r}".format(qty))
    return qty


class InventoryMixin:
    """库存相关方法。"""

    def receive(self, sku, qty):
        _validate_qty(qty)
        if sku not in self.products:
            raise NotFoundError("商品不存在: {!r}".format(sku))
        self.stock_levels[sku]["on_hand"] += qty
        self._append_stock_log(sku, qty, "receive")
        return self.stock(sku)

    def adjust(self, sku, delta, reason):
        if isinstance(delta, bool) or not isinstance(delta, int):
            raise ValidationError("调整量必须是 int: {!r}".format(delta))
        if delta == 0:
            raise ValidationError("调整量不能为 0")
        if not isinstance(reason, str):
            raise ValidationError("原因必须是字符串: {!r}".format(reason))
        clean_reason = reason.strip()
        if not clean_reason:
            raise ValidationError("原因不能为空")

        if sku not in self.products:
            raise NotFoundError("商品不存在: {!r}".format(sku))

        new_on_hand = self.stock_levels[sku]["on_hand"] + delta
        if new_on_hand < self.stock_levels[sku]["reserved"]:
            raise StockError("调整后在手数量小于已预留数量")

        self.stock_levels[sku]["on_hand"] = new_on_hand
        self._append_stock_log(sku, delta, clean_reason)
        return self.stock(sku)

    def stock(self, sku):
        record = self.stock_levels.get(sku)
        if record is None:
            raise NotFoundError("商品不存在: {!r}".format(sku))
        return self._stock_dict(record)

    def set_reorder_level(self, sku, level):
        if isinstance(level, bool) or not isinstance(level, int):
            raise ValidationError("补货线必须是 int: {!r}".format(level))
        if level < 0:
            raise ValidationError("补货线不能为负")
        if sku not in self.products:
            raise NotFoundError("商品不存在: {!r}".format(sku))
        self.reorder[sku] = level
        return self.stock(sku)

    def low_stock(self):
        result = []
        for sku in sorted(self.products):
            level = self.reorder.get(sku, 0)
            if level <= 0:
                continue
            record = self.stock_levels[sku]
            available = record["on_hand"] - record["reserved"]
            if available <= level:
                result.append(
                    {"sku": sku, "available": available, "reorder_level": level}
                )
        return result

    def stock_log(self, sku):
        if sku not in self.products:
            raise NotFoundError("商品不存在: {!r}".format(sku))
        return [dict(entry) for entry in self.stock_logs.get(sku, [])]

    def _append_stock_log(self, sku, change, reason):
        self.stock_logs.setdefault(sku, []).append(
            {"at": self._event_time(), "change": change, "reason": reason}
        )

    @staticmethod
    def _stock_dict(record):
        return {
            "on_hand": record["on_hand"],
            "reserved": record["reserved"],
            "available": record["on_hand"] - record["reserved"],
        }
