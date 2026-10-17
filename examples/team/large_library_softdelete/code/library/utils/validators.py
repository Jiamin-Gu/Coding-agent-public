def valid_isbn(isbn: str) -> bool:
    """13 位数字的 ISBN（可以带连字符）。"""
    digits = isbn.replace("-", "")
    return len(digits) == 13 and digits.isdigit()


def valid_email(email: str) -> bool:
    name, _, domain = email.partition("@")
    return bool(name) and "." in domain
