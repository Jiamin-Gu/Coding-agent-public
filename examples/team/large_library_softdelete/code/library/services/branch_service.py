from ..errors import ValidationError


class BranchService:
    def __init__(self, branches):
        self.branches = branches

    def create(self, name, city):
        if not name.strip() or not city.strip():
            raise ValidationError("分馆名称和城市不能为空")
        return self.branches.add(name=name.strip(), city=city.strip())

    def remove(self, branch_id):
        self.branches.delete(branch_id)
