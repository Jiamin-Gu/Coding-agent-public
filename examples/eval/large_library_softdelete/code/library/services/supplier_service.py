from ..errors import ValidationError


class SupplierService:
    def __init__(self, suppliers):
        self.suppliers = suppliers

    def create(self, name, contact=""):
        if not name.strip():
            raise ValidationError("供应商名称不能为空")
        return self.suppliers.add(name=name.strip(), contact=contact)

    def remove(self, supplier_id):
        self.suppliers.delete(supplier_id)
