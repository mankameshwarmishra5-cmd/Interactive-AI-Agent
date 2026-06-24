"""
tools/calculator.py — Safe arithmetic calculator tool.

Uses Python's ast module to evaluate math expressions without exec/eval risks.
Supports: +, -, *, /, //, %, **, parentheses, and basic numeric literals.
"""

import ast
import operator
from typing import Union

from tools.base import Tool

# Allowed AST node types and corresponding operators
_ALLOWED_OPS = {
    ast.Add:      operator.add,
    ast.Sub:      operator.sub,
    ast.Mult:     operator.mul,
    ast.Div:      operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod:      operator.mod,
    ast.Pow:      operator.pow,
    ast.USub:     operator.neg,
    ast.UAdd:     operator.pos,
}

_MAX_RESULT = 1e15  # Guard against astronomically large results


def _safe_eval(node: ast.AST) -> Union[int, float]:
    """Recursively evaluates an AST node using only allowed operations."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_OPS:
            raise ValueError(f"Unsupported operator: {op_type.__name__}")
        left = _safe_eval(node.left)
        right = _safe_eval(node.right)
        if op_type == ast.Div and right == 0:
            raise ZeroDivisionError("Division by zero.")
        result = _ALLOWED_OPS[op_type](left, right)
        if abs(result) > _MAX_RESULT:
            raise OverflowError("Result too large to display.")
        return result
    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_OPS:
            raise ValueError(f"Unsupported unary operator: {op_type.__name__}")
        return _ALLOWED_OPS[op_type](_safe_eval(node.operand))
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    raise ValueError(f"Unsupported expression type: {type(node).__name__}")


class CalculatorTool(Tool):
    """Evaluates safe arithmetic expressions."""

    @property
    def name(self) -> str:
        return "calculator"

    @property
    def description(self) -> str:
        return "Evaluates arithmetic expressions (e.g. '2 + 2', '(10 * 5) / 2', '2 ** 8')."

    def execute(self, argument: str) -> str:
        """
        Parses and evaluates *argument* as an arithmetic expression.

        Args:
            argument: A string containing a math expression. Non-math text
                      before/after the expression is stripped automatically.

        Returns:
            A Markdown-formatted result string.
        """
        import re

        # Extract the numeric expression from the argument
        expr = re.sub(r"[^0-9+\-*/().% \t]", "", argument).strip()
        if not expr:
            return "❌ No valid mathematical expression found. Example: `2 + 2`"

        try:
            tree = ast.parse(expr, mode="eval")
            result = _safe_eval(tree)

            # Format result: integer if whole number
            if isinstance(result, float) and result.is_integer():
                result = int(result)
                formatted = f"{result:,}"
            else:
                formatted = f"{result:,.6g}"

            return f"**`{expr}`** = **{formatted}**"

        except ZeroDivisionError:
            return "❌ **Division by zero** — cannot divide by zero."
        except OverflowError as exc:
            return f"❌ **Overflow** — {exc}"
        except Exception as exc:
            return f"❌ **Calculation error** — `{exc}`. Please check your expression."
