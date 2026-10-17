import re
from pathlib import Path

import pytest

from expr import evaluate


@pytest.mark.parametrize("expression, expected", [
    ("1 + 2 * 3", 7),
    ("(1+2)*3", 9),
    ("-(2+3)*2", -10),
    ("2 * -3", -6),
    ("10 / 4", 2.5),
    ("  3.5 + 0.5 ", 4),
    ("2 - 3 - 4", -5),
    ("2 * (3 + (4 - 1)) / 3", 4),
    ("--3", 3),
])
def test_values(expression, expected):
    assert evaluate(expression) == pytest.approx(expected)


@pytest.mark.parametrize("bad", ["(1+2", "1 + a", "", "1 +", "2 3", "()"])
def test_invalid(bad):
    with pytest.raises(ValueError):
        evaluate(bad)


def test_division_by_zero():
    with pytest.raises(ZeroDivisionError):
        evaluate("1 / (2 - 2)")


def test_no_eval():
    source = Path("expr.py").read_text(encoding="utf-8")
    assert not re.search(r"\b(eval|exec)\s*\(", source)
