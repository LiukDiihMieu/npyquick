# SPDX-License-Identifier: GPL-3.0-or-later

"""Safe arithmetic expression evaluator for pixel-size input, shared by the
desktop dialog (views/pixel_size_dialog.py) and the web dialog
(serve/pixel_size_dialog.py) so both parse "3.45/10"-style expressions
identically instead of maintaining two copies.

ast-based rather than eval(): only a fixed whitelist of numeric BinOp/UnaryOp
nodes is allowed, so there's no way to reach names, calls, attribute access,
or anything else eval() would otherwise permit.
"""

from __future__ import annotations

import ast
import math
import operator

UNITS = ["px", "nm", "μm", "mm", "cm", "m", "km", "in", "ft", "yd", "mi", "None"]

_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARYOPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _arith(node):
    if isinstance(node, ast.Expression):
        return _arith(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        raise ValueError(f"unsupported constant: {node.value!r}")
    if isinstance(node, ast.BinOp):
        op = _BINOPS.get(type(node.op))
        if op is None:
            raise ValueError(f"operator {type(node.op).__name__} not allowed")
        return op(_arith(node.left), _arith(node.right))
    if isinstance(node, ast.UnaryOp):
        op = _UNARYOPS.get(type(node.op))
        if op is None:
            raise ValueError(f"operator {type(node.op).__name__} not allowed")
        return op(_arith(node.operand))
    raise ValueError("only arithmetic expressions are allowed")


def eval_expr(text: str) -> float:
    text = text.strip()
    if not text:
        raise ValueError("empty expression")
    tree = ast.parse(text, mode="eval")
    result = float(_arith(tree))
    if not math.isfinite(result):
        raise ValueError("pixel size must be finite")
    if result <= 0:
        raise ValueError("pixel size must be positive")
    return result


def format_unit(unit: str) -> str:
    """Return unit for display ('' if 'None') — same rule as
    core.coord.PixelTransform.format_unit, duplicated here only because this
    module has no PixelTransform instance handy (just a raw unit string)."""
    return "" if unit == "None" else unit
