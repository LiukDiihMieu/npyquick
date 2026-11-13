from __future__ import annotations

import pytest

from npyquick.core.pixel_expr import eval_expr


@pytest.mark.parametrize("expr,expected", [
    ("1", 1.0),
    ("1.5", 1.5),
    ("3.45/10", 0.345),
    ("2*3+1", 7.0),
    ("2**0.5", 2 ** 0.5),
    ("(1+2)/3", 1.0),
    ("--5", 5.0),
    ("10 % 3", 1.0),
    ("7 // 2", 3.0),
])
def test_accepts_arithmetic(expr, expected):
    assert eval_expr(expr) == pytest.approx(expected)


@pytest.mark.parametrize("expr", [
    "inf",
    "nan",
    "pi",
    "e",
    "sqrt(2)",
    "factorial(10)",
    "(1).__class__",
    "1+a",
])
def test_rejects_names_and_calls(expr):
    with pytest.raises(ValueError):
        eval_expr(expr)


@pytest.mark.parametrize("expr", ["0", "-1", "-3.5", "0.0"])
def test_rejects_non_positive(expr):
    with pytest.raises(ValueError, match="positive"):
        eval_expr(expr)


def test_rejects_empty():
    with pytest.raises(ValueError, match="empty"):
        eval_expr("")
    with pytest.raises(ValueError, match="empty"):
        eval_expr("   ")


def test_rejects_overflow_to_inf():
    # 1e308 * 10 overflows float -> inf; must be rejected, not silently accepted
    with pytest.raises((ValueError, OverflowError)):
        eval_expr("1e308 * 10")


def test_rejects_syntax_error():
    with pytest.raises((ValueError, SyntaxError)):
        eval_expr("1 +")
