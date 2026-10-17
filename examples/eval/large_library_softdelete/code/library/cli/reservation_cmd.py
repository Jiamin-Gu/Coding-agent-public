def format_reservation(item):
    """把预约格式化成一行文字。"""
    return f"#{item.id} book_id={item.book_id} member_id={item.member_id}"


def print_reservation_list(repo):
    items = repo.list()
    if not items:
        print("（没有预约）")
    for item in items:
        print(format_reservation(item))
