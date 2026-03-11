from __future__ import annotations

import asyncio
import collections
import contextlib
import datetime
import functools
import io
import itertools
import json
import logging
import math
import random
import re
import string
from typing import Any

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 10
MAX_OUTPUT_CHARS = 2000

# Pre-approved safe builtins
_SAFE_BUILTINS: dict[str, Any] = {
    "print": print,
    "len": len, "range": range, "enumerate": enumerate,
    "zip": zip, "map": map, "filter": filter,
    "sorted": sorted, "reversed": reversed,
    "list": list, "dict": dict, "set": set, "tuple": tuple, "frozenset": frozenset,
    "str": str, "int": int, "float": float, "bool": bool, "bytes": bytes,
    "abs": abs, "round": round, "min": min, "max": max, "sum": sum,
    "any": any, "all": all,
    "isinstance": isinstance, "issubclass": issubclass, "type": type,
    "repr": repr, "hex": hex, "oct": oct, "bin": bin, "chr": chr, "ord": ord,
    "hasattr": hasattr, "getattr": getattr, "setattr": setattr,
    "iter": iter, "next": next, "callable": callable,
    "divmod": divmod, "pow": pow, "hash": hash,
    "True": True, "False": False, "None": None,
    "Exception": Exception, "ValueError": ValueError, "TypeError": TypeError,
    "KeyError": KeyError, "IndexError": IndexError, "AttributeError": AttributeError,
    "StopIteration": StopIteration, "RuntimeError": RuntimeError,
}

_SAFE_GLOBALS: dict[str, Any] = {
    "__builtins__": _SAFE_BUILTINS,
    "math": math,
    "random": random,
    "json": json,
    "datetime": datetime,
    "re": re,
    "string": string,
    "collections": collections,
    "itertools": itertools,
    "functools": functools,
}


async def run_python(code: str) -> str:
    """Execute Python code in a sandboxed environment and return the output."""

    def _exec() -> str:
        stdout_buf = io.StringIO()
        local_vars: dict = {}
        try:
            compiled = compile(code, "<sandbox>", "exec")
            with contextlib.redirect_stdout(stdout_buf):
                exec(compiled, dict(_SAFE_GLOBALS), local_vars)  # noqa: S102
        except Exception as e:
            captured = stdout_buf.getvalue()
            err = f"{type(e).__name__}: {e}"
            return f"{captured}\n{err}".strip() if captured else err

        output = stdout_buf.getvalue()
        if not output:
            # Show the last assigned variable if nothing was printed
            last = next(reversed(local_vars.values()), None) if local_vars else None
            if last is not None:
                output = repr(last)
        if not output:
            output = "(no output)"
        if len(output) > MAX_OUTPUT_CHARS:
            output = output[:MAX_OUTPUT_CHARS] + f"\n[Output truncated at {MAX_OUTPUT_CHARS} chars]"
        return output

    try:
        return await asyncio.wait_for(asyncio.to_thread(_exec), timeout=TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        return f"Execution timed out after {TIMEOUT_SECONDS} seconds."
    except Exception as e:
        return f"Execution error: {e}"


def make_code_runner_tool() -> dict:
    return {"name": "run_python", "fn": run_python}
