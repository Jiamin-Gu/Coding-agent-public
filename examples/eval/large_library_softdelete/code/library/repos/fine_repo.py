from __future__ import annotations

from ..models.fine import Fine
from .base_repo import BaseRepo


class FineRepo(BaseRepo):
    """罚款的存储（保存在内存里）。"""

    model_cls = Fine
    entity_type = "fine"
    label = "罚款"

    def for_member(self, member_id) -> list[Fine]:
        """某个会员的所有罚款。"""
        return [i for i in self.list() if i.member_id == member_id]
