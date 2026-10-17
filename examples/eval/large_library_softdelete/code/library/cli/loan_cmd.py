def format_loan(item):
    """把借阅记录格式化成一行文字。"""
    return f"#{item.id} book_id={item.book_id} member_id={item.member_id} due={item.due} returned={item.returned}"


def print_loan_list(repo):
    items = repo.list()
    if not items:
        print("（没有借阅记录）")
    for item in items:
        print(format_loan(item))
