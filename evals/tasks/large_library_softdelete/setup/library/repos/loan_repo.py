from __future__ import annotations

from ..errors import NotFoundError
from ..models.loan import Loan


class LoanRepo:
    """借阅记录的存储（保存在内存里）。"""

    def __init__(self):
        self._items: dict[int, Loan] = {}
        self._next_id = 1

    def add(self, **fields) -> Loan:
        item = Loan(id=self._next_id, **fields)
        self._items[item.id] = item
        self._next_id += 1
        return item

    def get(self, item_id) -> Loan:
        if item_id not in self._items:
            raise NotFoundError(f"借阅记录不存在：{item_id}")
        return self._items[item_id]

    def list(self) -> list[Loan]:
        return [self._items[k] for k in sorted(self._items)]

    def update(self, item_id, **changes) -> Loan:
        item = self.get(item_id)
        for field, value in changes.items():
            if field == "id" or not hasattr(item, field):
                raise ValueError(f"不能修改字段：{field}")
            setattr(item, field, value)
        return item

    def delete(self, item_id) -> None:
        self.get(item_id)
        del self._items[item_id]

    def for_book(self, book_id) -> list[Loan]:
        """某本书的所有借阅记录。"""
        return [i for i in self.list() if i.book_id == book_id]

    def for_member(self, member_id) -> list[Loan]:
        """某个会员的所有借阅记录。"""
        return [i for i in self.list() if i.member_id == member_id]
