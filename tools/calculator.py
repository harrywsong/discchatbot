from __future__ import annotations

import ast
import math
import operator

# Safe operator mapping
_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
    ast.BitAnd: operator.and_,
    ast.BitOr: operator.or_,
    ast.BitXor: operator.xor,
}

# Safe names/functions/constants
_SAFE_NAMES = {
    "abs": abs, "round": round, "min": min, "max": max,
    "sum": sum, "int": int, "float": float,
    "pi": math.pi, "e": math.e, "tau": math.tau,
    "sqrt": math.sqrt, "log": math.log, "log2": math.log2, "log10": math.log10,
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "asin": math.asin, "acos": math.acos, "atan": math.atan, "atan2": math.atan2,
    "ceil": math.ceil, "floor": math.floor, "factorial": math.factorial,
    "degrees": math.degrees, "radians": math.radians,
    "inf": math.inf,
}


def _eval_node(node):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float, complex)):
            return node.value
        raise ValueError(f"Unsupported constant: {node.value!r}")
    elif isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _OPERATORS:
            raise ValueError(f"Unsupported operator: {op_type.__name__}")
        return _OPERATORS[op_type](_eval_node(node.left), _eval_node(node.right))
    elif isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _OPERATORS:
            raise ValueError(f"Unsupported unary operator: {op_type.__name__}")
        return _OPERATORS[op_type](_eval_node(node.operand))
    elif isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("Only simple function calls allowed")
        fn_name = node.func.id
        if fn_name not in _SAFE_NAMES:
            raise ValueError(f"Unknown function: {fn_name}")
        args = [_eval_node(a) for a in node.args]
        return _SAFE_NAMES[fn_name](*args)
    elif isinstance(node, ast.Name):
        if node.id not in _SAFE_NAMES:
            raise ValueError(f"Unknown name: {node.id}")
        return _SAFE_NAMES[node.id]
    elif isinstance(node, ast.Expression):
        return _eval_node(node.body)
    else:
        raise ValueError(f"Unsupported expression type: {type(node).__name__}")


async def calculate(expression: str) -> str:
    """Safely evaluate a mathematical expression."""
    try:
        tree = ast.parse(expression.strip(), mode="eval")
        result = _eval_node(tree.body)
        if isinstance(result, float):
            if result == int(result) and abs(result) < 1e15:
                return str(int(result))
            return f"{result:.10g}"
        return str(result)
    except ZeroDivisionError:
        return "Error: Division by zero"
    except Exception as e:
        return f"Error: {e}"


def make_calculator_tool() -> dict:
    return {"name": "calculate", "fn": calculate}
