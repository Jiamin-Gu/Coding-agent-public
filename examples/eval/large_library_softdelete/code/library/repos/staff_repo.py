from __future__ import annotations

from ..models.staff import Staff
from .base_repo import BaseRepo


class StaffRepo(BaseRepo):
    """员工的存储（保存在内存里）。"""

    model_cls = Staff
    entity_type = "staff"
    label = "员工"

    def by_branch(self, branch_id) -> list[Staff]:
        """某个分馆的所有员工。"""
        return [i for i in self.list() if i.branch_id == branch_id]
