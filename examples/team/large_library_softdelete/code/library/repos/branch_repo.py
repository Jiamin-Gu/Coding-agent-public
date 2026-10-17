from __future__ import annotations

from ..models.branch import Branch
from .base import BaseRepo


class BranchRepo(BaseRepo):
    """分馆的存储（保存在内存里）。"""

    model = Branch
    label = "分馆"
    entity_type = "branch"
