"""简单的计算器模块，提供加、减、乘、除、幂五种运算。"""


def add(a, b):
    """返回 a 与 b 的和。"""
    return a + b


def sub(a, b):
    """返回 a 减去 b 的差。"""
    return a - b


def mul(a, b):
    """返回 a 与 b 的积。"""
    return a * b


def div(a, b):
    """返回 a 除以 b 的商，b 为 0 时抛出 ValueError。"""
    if b == 0:
        raise ValueError("除数不能为零")
    return a / b


def power(a, b):
    """返回 a 的 b 次幂。"""
    return a ** b
