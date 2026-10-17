def format_staff(item):
    """把员工格式化成一行文字。"""
    return f"#{item.id} name={item.name} branch_id={item.branch_id} role={item.role}"


def print_staff_list(repo):
    items = repo.list()
    if not items:
        print("（没有员工）")
    for item in items:
        print(format_staff(item))
