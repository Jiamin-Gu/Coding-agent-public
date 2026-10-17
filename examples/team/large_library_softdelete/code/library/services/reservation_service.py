from ..errors import ValidationError

MAX_RESERVATIONS = 3


class ReservationService:
    def __init__(self, reservations, books, members):
        self.reservations = reservations
        self.books = books
        self.members = members

    def reserve(self, book_id, member_id):
        self.books.get(book_id)
        self.members.get(member_id)
        if len(self.reservations.for_member(member_id)) >= MAX_RESERVATIONS:
            raise ValidationError(f"每位会员最多预约 {MAX_RESERVATIONS} 本书")
        return self.reservations.add(book_id=book_id, member_id=member_id)

    def cancel(self, reservation_id):
        self.reservations.delete(reservation_id)
