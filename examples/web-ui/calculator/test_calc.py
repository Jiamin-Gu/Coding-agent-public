"""calc 模块的 pytest 测试。"""

import pytest

from calc import add, div, mul, power, sub


def test_add():
    assert add(2, 3) == 5
    assert add(-1, 1) == 0
    assert add(0.1, 0.2) == pytest.approx(0.3)


def test_sub():
    assert sub(5, 3) == 2
    assert sub(3, 5) == -2


def test_mul():
    assert mul(4, 3) == 12
    assert mul(-2, 3) == -6
    assert mul(0, 5) == 0


def test_div():
    assert div(6, 3) == 2
    assert div(1, 2) == 0.5
    assert div(-6, 2) == -3


def test_div_by_zero():
    with pytest.raises(ValueError):
        div(1, 0)
    with pytest.raises(ValueError):
        div(0, 0)


def test_power():
    assert power(2, 3) == 8
    assert power(5, 0) == 1
    assert power(0, 5) == 0
    assert power(2, -2) == 0.25
    assert power(-2, 3) == -8
    assert power(4, 0.5) == pytest.approx(2.0)
