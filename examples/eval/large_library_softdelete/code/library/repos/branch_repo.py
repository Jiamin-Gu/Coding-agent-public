from __future__ import annotations

from ..models.branch import Branch
from .base_repo import BaseRepo


class BranchRepo(BaseRepo):
    """分馆的存储（保存在内存里）。"""

    model_cls = Branch
    entity_type = "branch"
    label = "分馆"
