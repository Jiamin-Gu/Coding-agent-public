def format_member(item):
    """把会员格式化成一行文字。"""
    return f"#{item.id} name={item.name} email={item.email} level={item.level}"


def print_member_list(repo):
    items = repo.list()
    if not items:
        print("（没有会员）")
    for item in items:
        print(format_member(item))
