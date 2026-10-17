"""Inventory mixin.

Operates on the shared state attributes documented in the project contract
(``self._stock`` and ``self._logs``), created by ``Shop``.
"""

import copy

from ._util import norm_text, now_iso, require_int, validate_qty
from .errors import NotFoundError, StockError, ValidationError


class InventoryMixin:
    """Stock level operations (SPEC section 4)."""

    # -- internal helpers -------------------------------------------------

    def _stock_state(self, sku):
        """Return the internal stock dict for ``sku`` or raise NotFoundError."""
        try:
            return self._stock[sku]
        except (KeyError, TypeError):
            raise NotFoundError(f"product {sku!r} not found")

    @staticmethod
    def _available(state):
        return state["on_hand"] - state["reserved"]

    # -- public API -------------------------------------------------------

    def receive(self, sku, qty):
        """Receive ``qty`` units into stock."""
        qty = validate_qty(qty)
        state = self._stock_state(sku)
        state["on_hand"] += qty
        self._logs[sku].append(
            {"at": now_iso(self._clock), "change": qty, "reason": "receive"}
        )
        return self.stock(sku)

    def adjust(self, sku, delta, reason):
        """Apply a stock adjustment; on_hand must not drop below reserved."""
        delta = require_int(delta, "delta")
        if delta == 0:
            raise ValidationError("delta must not be 0")
        reason = norm_text(reason, "reason")

        state = self._stock_state(sku)
        if state["on_hand"] + delta < state["reserved"]:
            raise StockError("adjustment would put on_hand below reserved")

        state["on_hand"] += delta
        self._logs[sku].append(
            {"at": now_iso(self._clock), "change": delta, "reason": reason}
        )
        return self.stock(sku)

    def stock(self, sku):
        """Return the stock levels of ``sku``."""
        state = self._stock_state(sku)
        return {
            "on_hand": state["on_hand"],
            "reserved": state["reserved"],
            "available": self._available(state),
        }

    def set_reorder_level(self, sku, level):
        """Set the reorder level for ``sku``."""
        level = require_int(level, "level")
        if level < 0:
            raise ValidationError("level must be >= 0")
        state = self._stock_state(sku)
        state["reorder_level"] = level
        return self.stock(sku)

    def low_stock(self):
        """Return products whose available stock is at or below the reorder level."""
        result = []
        for sku in sorted(self._stock):
            state = self._stock[sku]
            available = self._available(state)
            if state["reorder_level"] > 0 and available <= state["reorder_level"]:
                result.append(
                    {
                        "sku": sku,
                        "available": available,
                        "reorder_level": state["reorder_level"],
                    }
                )
        return result

    def stock_log(self, sku):
        """Return a copy of the stock movement log for ``sku``."""
        self._stock_state(sku)
        return copy.deepcopy(self._logs[sku])
