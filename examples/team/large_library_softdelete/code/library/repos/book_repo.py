from __future__ import annotations

from ..models.book import Book
from .base import BaseRepo


class BookRepo(BaseRepo):
    """图书的存储（保存在内存里）。"""

    model = Book
    label = "图书"
    entity_type = "book"

    def by_branch(self, branch_id) -> list[Book]:
        """某个分馆的所有图书。"""
        return [i for i in self.list() if i.branch_id == branch_id]
