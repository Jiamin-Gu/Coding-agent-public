"""The ``Shop`` facade combining every mixin and providing persistence."""

import json
import os
import tempfile
from datetime import datetime

from .catalog import CatalogMixin
from .coupons import CouponMixin
from .inventory import InventoryMixin
from .orders import OrdersMixin
from .pricing import PricingMixin
from .reports import ReportsMixin
from .storage import dump_state, load as _load_state


class Shop(
    CatalogMixin,
    InventoryMixin,
    PricingMixin,
    CouponMixin,
    OrdersMixin,
    ReportsMixin,
):
    """A small web shop core, sharing one bundle of mutable state."""

    def __init__(self, clock=None):
        self._clock = clock or datetime.now
        self._products = {}
        self._stock = {}
        self._logs = {}
        self._tiers = {}
        self._cat_discount = {}
        self._tax = {}
        self._coupons = {}
        self._orders = {}
        self._order_seq = 0

    def save(self, path):
        """Atomically write the whole shop state to a UTF-8 JSON file."""
        data = dump_state(self)
        directory = os.path.dirname(os.path.abspath(path))
        fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False)
            os.replace(tmp_path, path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    @classmethod
    def load(cls, path, clock=None):
        """Load a shop from an archive written by :meth:`save`."""
        return _load_state(cls, path, clock)
