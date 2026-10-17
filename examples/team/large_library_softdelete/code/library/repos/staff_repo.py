from __future__ import annotations

from ..models.staff import Staff
from .base import BaseRepo


class StaffRepo(BaseRepo):
    """员工的存储（保存在内存里）。"""

    model = Staff
    label = "员工"
    entity_type = "staff"

    def by_branch(self, branch_id) -> list[Staff]:
        """某个分馆的所有员工。"""
        return [i for i in self.list() if i.branch_id == branch_id]
