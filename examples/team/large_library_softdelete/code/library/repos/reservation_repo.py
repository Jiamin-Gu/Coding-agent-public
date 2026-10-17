from __future__ import annotations

from ..models.reservation import Reservation
from .base import BaseRepo


class ReservationRepo(BaseRepo):
    """预约的存储（保存在内存里）。"""

    model = Reservation
    label = "预约"
    entity_type = "reservation"

    def for_member(self, member_id) -> list[Reservation]:
        """某个会员的所有预约。"""
        return [i for i in self.list() if i.member_id == member_id]

    def for_book(self, book_id) -> list[Reservation]:
        """某本书的所有预约。"""
        return [i for i in self.list() if i.book_id == book_id]
