from ..errors import ValidationError
from ..utils.validators import valid_email

LEVELS = ("basic", "vip")


class MemberService:
    def __init__(self, members):
        self.members = members

    def register(self, name, email, level="basic"):
        if not valid_email(email):
            raise ValidationError(f"邮箱不合法：{email}")
        if level not in LEVELS:
            raise ValidationError(f"会员等级只能是 {LEVELS}")
        if any(m.email == email for m in self.members.list()):
            raise ValidationError(f"邮箱已被注册：{email}")
        return self.members.add(name=name, email=email, level=level)

    def upgrade(self, member_id):
        return self.members.update(member_id, level="vip")

    def remove(self, member_id):
        self.members.delete(member_id)
