def format_supplier(item):
    """把供应商格式化成一行文字。"""
    return f"#{item.id} name={item.name} contact={item.contact}"


def print_supplier_list(repo):
    items = repo.list()
    if not items:
        print("（没有供应商）")
    for item in items:
        print(format_supplier(item))
