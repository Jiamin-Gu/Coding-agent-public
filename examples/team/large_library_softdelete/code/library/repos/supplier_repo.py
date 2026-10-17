from __future__ import annotations

from ..models.supplier import Supplier
from .base import BaseRepo


class SupplierRepo(BaseRepo):
    """供应商的存储（保存在内存里）。"""

    model = Supplier
    label = "供应商"
    entity_type = "supplier"
