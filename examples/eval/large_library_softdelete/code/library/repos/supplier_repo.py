from __future__ import annotations

from ..models.supplier import Supplier
from .base_repo import BaseRepo


class SupplierRepo(BaseRepo):
    """供应商的存储（保存在内存里）。"""

    model_cls = Supplier
    entity_type = "supplier"
    label = "供应商"
