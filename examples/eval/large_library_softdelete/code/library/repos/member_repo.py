from __future__ import annotations

from ..models.member import Member
from .base_repo import BaseRepo


class MemberRepo(BaseRepo):
    """会员的存储（保存在内存里）。"""

    model_cls = Member
    entity_type = "member"
    label = "会员"

    def by_level(self, level) -> list[Member]:
        """某个等级的所有会员。"""
        return [i for i in self.list() if i.level == level]
