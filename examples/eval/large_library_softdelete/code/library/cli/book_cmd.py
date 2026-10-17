def format_book(item):
    """把图书格式化成一行文字。"""
    return f"#{item.id} title={item.title} author={item.author} isbn={item.isbn} branch_id={item.branch_id}"


def print_book_list(repo):
    items = repo.list()
    if not items:
        print("（没有图书）")
    for item in items:
        print(format_book(item))
