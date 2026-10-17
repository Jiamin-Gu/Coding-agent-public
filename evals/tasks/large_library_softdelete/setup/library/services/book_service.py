from ..errors import ValidationError
from ..utils.validators import valid_isbn


class BookService:
    def __init__(self, books, branches):
        self.books = books
        self.branches = branches

    def create(self, title, author, isbn, branch_id):
        if not valid_isbn(isbn):
            raise ValidationError(f"ISBN 不合法：{isbn}")
        self.branches.get(branch_id)  # 分馆必须存在
        return self.books.add(title=title, author=author, isbn=isbn, branch_id=branch_id)

    def move(self, book_id, branch_id):
        self.branches.get(branch_id)
        return self.books.update(book_id, branch_id=branch_id)

    def remove(self, book_id):
        self.books.delete(book_id)
