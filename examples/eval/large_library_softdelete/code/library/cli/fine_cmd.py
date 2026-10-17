def format_fine(item):
    """把罚款格式化成一行文字。"""
    return f"#{item.id} member_id={item.member_id} amount={item.amount} paid={item.paid}"


def print_fine_list(repo):
    items = repo.list()
    if not items:
        print("（没有罚款）")
    for item in items:
        print(format_fine(item))
