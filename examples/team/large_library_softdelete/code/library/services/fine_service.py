from ..errors import ValidationError


class FineService:
    def __init__(self, fines, members):
        self.fines = fines
        self.members = members

    def issue(self, member_id, amount):
        if amount <= 0:
            raise ValidationError("罚款金额必须为正（单位：分）")
        self.members.get(member_id)
        return self.fines.add(member_id=member_id, amount=amount)

    def pay(self, fine_id):
        return self.fines.update(fine_id, paid=True)

    def outstanding(self, member_id):
        """会员未缴的罚款总额（分）。"""
        return sum(f.amount for f in self.fines.for_member(member_id) if not f.paid)

    def remove(self, fine_id):
        self.fines.delete(fine_id)
