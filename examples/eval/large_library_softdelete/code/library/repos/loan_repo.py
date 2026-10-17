from __future__ import annotations

from ..models.loan import Loan
from .base_repo import BaseRepo


class LoanRepo(BaseRepo):
    """借阅记录的存储（保存在内存里）。"""

    model_cls = Loan
    entity_type = "loan"
    label = "借阅记录"

    def for_book(self, book_id) -> list[Loan]:
        """某本书的所有借阅记录。"""
        return [i for i in self.list() if i.book_id == book_id]

    def for_member(self, member_id) -> list[Loan]:
        """某个会员的所有借阅记录。"""
        return [i for i in self.list() if i.member_id == member_id]
