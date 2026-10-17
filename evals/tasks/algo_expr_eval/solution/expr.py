import re

TOKEN = re.compile(r"\s*(?:(\d+\.?\d*|\.\d+)|(.))")


def tokenize(s):
    tokens = []
    for number, op in TOKEN.findall(s):
        if number:
            tokens.append(float(number))
        elif op.strip():
            if op not in "+-*/()":
                raise ValueError(f"非法字符：{op}")
            tokens.append(op)
    return tokens


def evaluate(expression):
    tokens = tokenize(expression)
    pos = 0

    def peek():
        return tokens[pos] if pos < len(tokens) else None

    def take():
        nonlocal pos
        if pos >= len(tokens):
            raise ValueError("表达式不完整")
        pos += 1
        return tokens[pos - 1]

    def expr():
        value = term()
        while peek() in ("+", "-"):
            value = value + term() if take() == "+" else value - term()
        return value

    def term():
        value = factor()
        while peek() in ("*", "/"):
            if take() == "*":
                value *= factor()
            else:
                value /= factor()
        return value

    def factor():
        tok = take()
        if tok == "-":
            return -factor()
        if tok == "+":
            return factor()
        if tok == "(":
            value = expr()
            if take() != ")":
                raise ValueError("括号不匹配")
            return value
        if isinstance(tok, float):
            return tok
        raise ValueError(f"意外的符号：{tok}")

    if not tokens:
        raise ValueError("空表达式")
    result = expr()
    if pos != len(tokens):
        raise ValueError("多余的内容")
    return result
