from ..errors import ValidationError

ROLES = ("librarian", "manager")


class StaffService:
    def __init__(self, staff, branches):
        self.staff = staff
        self.branches = branches

    def hire(self, name, branch_id, role="librarian"):
        if role not in ROLES:
            raise ValidationError(f"岗位只能是 {ROLES}")
        self.branches.get(branch_id)
        if role == "manager" and any(s.role == "manager" for s in self.staff.by_branch(branch_id)):
            raise ValidationError("每个分馆只能有一位馆长")
        return self.staff.add(name=name, branch_id=branch_id, role=role)

    def remove(self, staff_id):
        self.staff.delete(staff_id)
