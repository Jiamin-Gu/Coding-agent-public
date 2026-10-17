"""库存：receive / adjust / stock / set_reorder_level / low_stock / stock_log。

以及给订单模块使用的内部助手 ``_reserve`` / ``_release`` / ``_consume`` /
``_available``。内部库存 dict 由商品目录在新增商品时初始化，结构为
``{"on_hand", "reserved", "reorder_level", "log"}``。
"""

from shopkit.errors import NotFoundError, StockError, ValidationError


class InventoryMixin:
    """库存相关方法，供 :class:`~shopkit.shop.Shop` 混入。"""

    # --- 辅助 -----------------------------------------------------------

    def _get_stock(self, sku) -> dict:
        """返回内部库存 dict（sku 非 str 或不存在 → 相应异常）。"""
        if not isinstance(sku, str):
            raise ValidationError(f"sku 必须是字符串，不能是 {type(sku).__name__}")
        try:
            return self._stock[sku]
        except KeyError:
            raise NotFoundError(f"商品不存在：{sku!r}") from None

    @staticmethod
    def _stock_view(entry: dict) -> dict:
        """把内部库存 dict 转成对外的 stock 视图。"""
        return {
            "on_hand": entry["on_hand"],
            "reserved": entry["reserved"],
            "available": entry["on_hand"] - entry["reserved"],
        }

    # --- 公开接口 -------------------------------------------------------

    def receive(self, sku, qty) -> dict:
        """入库 qty 件；先校验参数，再查 sku。"""
        if isinstance(qty, bool) or not isinstance(qty, int):
            raise ValidationError(f"qty 必须是 int，不能是 {type(qty).__name__}")
        if qty < 1:
            raise ValidationError("qty 必须大于等于 1")

        entry = self._get_stock(sku)
        # 先算好时间戳再改状态：clock 抛异常时不会留下半更新的库存
        now = self._now()
        entry["on_hand"] += qty
        entry["log"].append({"at": now, "change": qty, "reason": "receive"})
        return self._stock_view(entry)

    def adjust(self, sku, delta, reason) -> dict:
        """盘点调整 on_hand；调整后 on_hand < reserved → StockError。"""
        if isinstance(delta, bool) or not isinstance(delta, int):
            raise ValidationError(f"delta 必须是 int，不能是 {type(delta).__name__}")
        if delta == 0:
            raise ValidationError("delta 不能为 0")

        if not isinstance(reason, str):
            raise ValidationError(f"reason 必须是字符串，不能是 {type(reason).__name__}")
        clean_reason = reason.strip()
        if clean_reason == "":
            raise ValidationError("reason 不能为空")

        entry = self._get_stock(sku)
        new_on_hand = entry["on_hand"] + delta
        if new_on_hand < entry["reserved"]:
            raise StockError(
                f"调整后在手数量 {new_on_hand} 小于已预留数量 {entry['reserved']}"
            )

        # 先算好时间戳再改状态：clock 抛异常时不会留下半更新的库存
        now = self._now()
        entry["on_hand"] = new_on_hand
        entry["log"].append(
            {"at": now, "change": delta, "reason": clean_reason}
        )
        return self._stock_view(entry)

    def stock(self, sku) -> dict:
        """返回 ``{"on_hand", "reserved", "available"}``。"""
        return self._stock_view(self._get_stock(sku))

    def set_reorder_level(self, sku, level) -> dict:
        """设置补货线（level 为 int 且 >= 0）。"""
        if isinstance(level, bool) or not isinstance(level, int):
            raise ValidationError(f"level 必须是 int，不能是 {type(level).__name__}")
        if level < 0:
            raise ValidationError("level 不能为负数")

        entry = self._get_stock(sku)
        entry["reorder_level"] = level
        return self._stock_view(entry)

    def low_stock(self) -> list:
        """所有 reorder_level > 0 且 available <= reorder_level 的商品，按 sku 升序。"""
        result = []
        for sku in sorted(self._stock):
            entry = self._stock[sku]
            available = entry["on_hand"] - entry["reserved"]
            if entry["reorder_level"] > 0 and available <= entry["reorder_level"]:
                result.append(
                    {
                        "sku": sku,
                        "available": available,
                        "reorder_level": entry["reorder_level"],
                    }
                )
        return result

    def stock_log(self, sku) -> list:
        """按发生顺序返回库存流水（返回副本）。"""
        entry = self._get_stock(sku)
        return [dict(item) for item in entry["log"]]

    # --- 供 OrderMixin 使用（不记流水） --------------------------------

    def _reserve(self, sku, qty) -> None:
        """预留 qty 件（reserved += qty），不记流水。"""
        self._get_stock(sku)["reserved"] += qty

    def _release(self, sku, qty) -> None:
        """释放预留（reserved -= qty），不记流水。"""
        self._get_stock(sku)["reserved"] -= qty

    def _consume(self, sku, qty) -> None:
        """出库：on_hand -= qty 且 reserved -= qty，不记流水。"""
        entry = self._get_stock(sku)
        entry["on_hand"] -= qty
        entry["reserved"] -= qty

    def _available(self, sku) -> int:
        """可用库存 = on_hand - reserved。"""
        entry = self._get_stock(sku)
        return entry["on_hand"] - entry["reserved"]
