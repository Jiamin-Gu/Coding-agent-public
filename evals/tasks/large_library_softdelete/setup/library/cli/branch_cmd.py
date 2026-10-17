def format_branch(item):
    """把分馆格式化成一行文字。"""
    return f"#{item.id} name={item.name} city={item.city}"


def print_branch_list(repo):
    items = repo.list()
    if not items:
        print("（没有分馆）")
    for item in items:
        print(format_branch(item))
