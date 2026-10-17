"""算术表达式求值。

不使用 eval/exec，而是手写词法分析和递归下降解析。
支持整数、小数、+ - * /、括号、一元负号以及任意空格。
"""


def evaluate(expression: str) -> float:
    """计算算术表达式的值。

    非法表达式（空字符串、括号不匹配、非法字符等）抛出 ValueError；
    除以零抛出 ZeroDivisionError。
    """
    if not isinstance(expression, str):
        raise ValueError("expression must be a string")
    tokens = _tokenize(expression)
    if not tokens:
        raise ValueError("empty expression")
    parser = _Parser(tokens)
    result = parser.parse_expression()
    if not parser.at_end():
        raise ValueError("unexpected token: %r" % parser.peek())
    return result


# ---------------------------------------------------------------------------
# 词法分析
# ---------------------------------------------------------------------------

def _tokenize(expression):
    tokens = []
    i = 0
    n = len(expression)
    while i < n:
        ch = expression[i]
        if ch.isspace():
            i += 1
            continue
        if ch in "+-*/()":
            tokens.append(ch)
            i += 1
            continue
        if ch.isdigit() or ch == ".":
            j = i
            dot_count = 0
            while j < n and (expression[j].isdigit() or expression[j] == "."):
                if expression[j] == ".":
                    dot_count += 1
                j += 1
            number = expression[i:j]
            if dot_count > 1 or number == ".":
                raise ValueError("invalid number: %r" % number)
            tokens.append(number)
            i = j
            continue
        raise ValueError("invalid character: %r" % ch)
    return tokens


# ---------------------------------------------------------------------------
# 递归下降解析
# ---------------------------------------------------------------------------
#
# phrase : expression EOF
# expression : term (('+' | '-') term)*
# term : factor (('*' | '/') factor)*
# factor : '-' factor | primary
# primary : NUMBER | '(' expression ')'

class _Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def at_end(self):
        return self.pos >= len(self.tokens)

    def peek(self):
        if self.at_end():
            return None
        return self.tokens[self.pos]

    def advance(self):
        token = self.tokens[self.pos]
        self.pos += 1
        return token

    def parse_expression(self):
        value = self.parse_term()
        while not self.at_end() and self.peek() in ("+", "-"):
            op = self.advance()
            rhs = self.parse_term()
            if op == "+":
                value += rhs
            else:
                value -= rhs
        return value

    def parse_term(self):
        value = self.parse_factor()
        while not self.at_end() and self.peek() in ("*", "/"):
            op = self.advance()
            rhs = self.parse_factor()
            if op == "*":
                value *= rhs
            else:
                if rhs == 0:
                    raise ZeroDivisionError("division by zero")
                value /= rhs
        return value

    def parse_factor(self):
        if self.peek() == "-":
            self.advance()
            return -self.parse_factor()
        return self.parse_primary()

    def parse_primary(self):
        token = self.peek()
        if token is None:
            raise ValueError("unexpected end of expression")
        if token == "(":
            self.advance()
            value = self.parse_expression()
            if self.at_end() or self.peek() != ")":
                raise ValueError("missing closing parenthesis")
            self.advance()
            return value
        if token == ")":
            raise ValueError("unexpected ')'")
        # 数字
        self.advance()
        return float(token)
