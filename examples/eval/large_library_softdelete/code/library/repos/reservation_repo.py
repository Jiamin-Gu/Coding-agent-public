from __future__ import annotations

from ..models.reservation import Reservation
from .base_repo import BaseRepo


class ReservationRepo(BaseRepo):
    """预约的存储（保存在内存里）。"""

    model_cls = Reservation
    entity_type = "reservation"
    label = "预约"

    def for_member(self, member_id) -> list[Reservation]:
        """某个会员的所有预约。"""
        return [i for i in self.list() if i.member_id == member_id]

    def for_book(self, book_id) -> list[Reservation]:
        """某本书的所有预约。"""
        return [i for i in self.list() if i.book_id == book_id]
