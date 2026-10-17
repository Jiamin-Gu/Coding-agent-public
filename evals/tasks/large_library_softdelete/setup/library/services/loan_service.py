from ..errors import ValidationError
from ..utils.dates import add_days


class LoanService:
    LOAN_DAYS = 14

    def __init__(self, loans, books, members, clock):
        self.loans = loans
        self.books = books
        self.members = members
        self.clock = clock

    def borrow(self, book_id, member_id):
        self.books.get(book_id)
        self.members.get(member_id)
        if any(not l.returned for l in self.loans.for_book(book_id)):
            raise ValidationError(f"图书已借出：{book_id}")
        due = add_days(self.clock.today(), self.LOAN_DAYS)
        return self.loans.add(book_id=book_id, member_id=member_id, due=due)

    def give_back(self, loan_id):
        loan = self.loans.get(loan_id)
        if loan.returned:
            raise ValidationError("这次借阅已经归还")
        return self.loans.update(loan_id, returned=True)

    def active_count(self, member_id):
        return sum(1 for l in self.loans.for_member(member_id) if not l.returned)

    def remove(self, loan_id):
        self.loans.delete(loan_id)
