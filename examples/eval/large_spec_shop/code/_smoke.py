from datetime import datetime
import json
from shopkit import Shop

s = Shop(clock=lambda: datetime(2026, 3, 1, 9, 30, 0))
print(s.add_product("A-1", "Apple", "10.00", "Food"))
print(s.add_coupon(" save10 ", "percent", 10))
s.set_category_discount("food", 10)
s.set_tax_rate("food", "9")
q = s.quote([{"sku": "A-1", "qty": 3}], coupon="save10")
print(json.dumps(q, ensure_ascii=False, indent=1))
