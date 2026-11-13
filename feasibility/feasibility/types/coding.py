"""Coding feasibility.

The model fixes the code. Three checks:

1. Every ``.py`` file named in the instruction is in the task folder.
2. An imported module really does not exist. Comments and strings are ignored.
   A module exists when it is builtin, in the standard library, installed, or
   a file in the task folder. ``find_spec`` is a last look, so a module that
   the catalog missed is still treated as present.
3. A test assertion that does not call the library is already false. The AST
   evaluates only literals and builtins (``len('abc') == 4``). A call into
   the library is left for the model, because that function can be rewritten.
"""

from __future__ import annotations

import ast
import importlib.metadata
import importlib.util
import io
import pkgutil
import re
import sys
import tokenize
from pathlib import Path

_CATALOG: set[str] | None = None


def can_answer(instruction: str, work_dir: Path) -> tuple[bool, str]:
    names = _py_names(instruction)
    if not names:
        return True, "в условии нет имён .py, не пропускаем"

    missing = [name for name in names if not (work_dir / name).is_file()]
    if missing:
        return False, f"в каталоге нет {', '.join(missing)}"

    for name in names:
        text = (work_dir / name).read_text(encoding="utf-8")
        absent = _absent_import(text, work_dir)
        if absent:
            return False, f"библиотеки {absent} не существует"

    for path in sorted(work_dir.glob("test_*.py")):
        broken = _broken_test(path.read_text(encoding="utf-8"))
        if broken:
            return False, broken
    return True, "файлы на месте, импорты существуют, тесты не противоречат себе"


def _py_names(instruction: str) -> list[str]:
    found = re.findall(r"((?:[\w.-]+/)*)([\w.-]+\.py)\b", instruction)
    names: list[str] = []
    for folder, filename in found:
        name = f"{folder}{filename}"
        if name not in names:
            names.append(name)
    return names


def _absent_import(text: str, work_dir: Path) -> str | None:
    for name in _imported_modules(text):
        if _module_exists(name, work_dir):
            continue
        return name
    return None


def _imported_modules(text: str) -> list[str]:
    # tokenize drops comments and string literals, so a commented import is invisible.
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return []

    names: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.type == tokenize.NAME and token.string == "from":
            index = _read_from(tokens, index + 1, names)
            continue
        if token.type == tokenize.NAME and token.string == "import":
            index = _read_import(tokens, index + 1, names)
            continue
        index += 1
    return names


def _read_from(tokens: list[tokenize.TokenInfo], index: int, names: list[str]) -> int:
    relative = False
    while index < len(tokens) and tokens[index].string == ".":
        relative = True
        index += 1
    if not relative and index < len(tokens) and tokens[index].type == tokenize.NAME:
        names.append(tokens[index].string)
    while index < len(tokens) and tokens[index].type not in (tokenize.NEWLINE, tokenize.ENDMARKER):
        index += 1
    return index + 1


def _read_import(tokens: list[tokenize.TokenInfo], index: int, names: list[str]) -> int:
    expect_module = True
    while index < len(tokens) and tokens[index].type not in (tokenize.NEWLINE, tokenize.ENDMARKER):
        token = tokens[index]
        if token.type in (tokenize.NL, tokenize.COMMENT):
            index += 1
            continue
        if expect_module and token.type == tokenize.NAME:
            names.append(token.string)
            expect_module = False
            index += 1
            while index < len(tokens) and tokens[index].string == ".":
                index += 1
                if index < len(tokens) and tokens[index].type == tokenize.NAME:
                    index += 1
            continue
        if token.string == "as":
            index += 1
            if index < len(tokens) and tokens[index].type == tokenize.NAME:
                index += 1
            continue
        if token.string == ",":
            expect_module = True
            index += 1
            continue
        index += 1
    return index + 1


def _module_exists(name: str, work_dir: Path) -> bool:
    if name in _catalog() or name in _local_modules(work_dir):
        return True
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _catalog() -> set[str]:
    global _CATALOG
    if _CATALOG is None:
        names = set(sys.builtin_module_names)
        names.update(getattr(sys, "stdlib_module_names", ()))
        try:
            names.update(importlib.metadata.packages_distributions())
        except Exception:
            pass
        try:
            for module in pkgutil.iter_modules():
                names.add(module.name)
        except Exception:
            pass
        _CATALOG = names
    return _CATALOG


_SAFE_CALLS = {
    "abs": abs,
    "all": all,
    "any": any,
    "len": len,
    "max": max,
    "min": min,
    "round": round,
    "sorted": sorted,
    "sum": sum,
}

_COMPARE = {
    "assertEqual": lambda left, right: left == right,
    "assertEquals": lambda left, right: left == right,
    "assertNotEqual": lambda left, right: left != right,
    "assertIs": lambda left, right: left is right,
    "assertIsNot": lambda left, right: left is not right,
    "assertIn": lambda left, right: left in right,
    "assertNotIn": lambda left, right: left not in right,
    "assertGreater": lambda left, right: left > right,
    "assertGreaterEqual": lambda left, right: left >= right,
    "assertLess": lambda left, right: left < right,
    "assertLessEqual": lambda left, right: left <= right,
    "assertListEqual": lambda left, right: left == right,
    "assertTupleEqual": lambda left, right: left == right,
    "assertSetEqual": lambda left, right: left == right,
    "assertDictEqual": lambda left, right: left == right,
    "assertCountEqual": lambda left, right: sorted(left) == sorted(right),
    "assertMultiLineEqual": lambda left, right: left == right,
    "assertSequenceEqual": lambda left, right: left == right,
}


def _broken_test(text: str) -> str | None:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return "тест не разбирается, править его нельзя"
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _assert_name(node.func)
        if name is None or len(node.args) < 1:
            continue
        try:
            arguments = [_eval_pure(arg) for arg in node.args]
        except Exception:
            return f"тест нельзя починить: {ast.unparse(node)} падает"
        if any(value is _UNKNOWN for value in arguments):
            continue
        holds = _assertion_holds(name, arguments)
        if holds is False:
            return f"тест нельзя починить: {ast.unparse(node)} не выполняется"
    return None


def _assert_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Attribute):
        return func.attr if func.attr.startswith("assert") else None
    if isinstance(func, ast.Name) and func.id.startswith("assert"):
        return func.id
    return None


def _assertion_holds(name: str, arguments: list[object]) -> bool | None:
    try:
        if name in _COMPARE and len(arguments) >= 2:
            return bool(_COMPARE[name](arguments[0], arguments[1]))
        if name == "assertTrue":
            return bool(arguments[0])
        if name == "assertFalse":
            return not bool(arguments[0])
        if name == "assertIsNone":
            return arguments[0] is None
        if name == "assertIsNotNone":
            return arguments[0] is not None
    except Exception:
        return False
    return None


class _Unknown:
    pass


_UNKNOWN = _Unknown()


def _eval_pure(node: ast.expr) -> object:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.List):
        return _eval_sequence(node.elts, list)
    if isinstance(node, ast.Tuple):
        return _eval_sequence(node.elts, tuple)
    if isinstance(node, ast.Set):
        return _eval_sequence(node.elts, set)
    if isinstance(node, ast.Dict):
        keys = [_eval_pure(key) for key in node.keys if key is not None]
        values = [_eval_pure(value) for value in node.values]
        if _UNKNOWN in keys or _UNKNOWN in values or None in node.keys:
            return _UNKNOWN
        return dict(zip(keys, values))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.Not, ast.UAdd, ast.USub)):
        value = _eval_pure(node.operand)
        if value is _UNKNOWN:
            return _UNKNOWN
        if isinstance(node.op, ast.Not):
            return not value
        if isinstance(node.op, ast.USub):
            return -value
        return +value
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow)):
        left, right = _eval_pure(node.left), _eval_pure(node.right)
        if left is _UNKNOWN or right is _UNKNOWN:
            return _UNKNOWN
        return _apply_bin(node.op, left, right)
    if isinstance(node, ast.BoolOp):
        values = [_eval_pure(item) for item in node.values]
        if _UNKNOWN in values:
            return _UNKNOWN
        if isinstance(node.op, ast.And):
            return all(values)
        return any(values)
    if isinstance(node, ast.Compare):
        left = _eval_pure(node.left)
        if left is _UNKNOWN:
            return _UNKNOWN
        for op, comparator in zip(node.ops, node.comparators):
            right = _eval_pure(comparator)
            if right is _UNKNOWN or not _apply_cmp(op, left, right):
                return _UNKNOWN if right is _UNKNOWN else False
            left = right
        return True
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _SAFE_CALLS and not node.keywords:
        args = [_eval_pure(arg) for arg in node.args]
        if _UNKNOWN in args:
            return _UNKNOWN
        try:
            return _SAFE_CALLS[node.func.id](*args)
        except Exception:
            return _UNKNOWN
    if isinstance(node, ast.Name) and node.id in {"True", "False", "None"}:
        return {"True": True, "False": False, "None": None}[node.id]
    return _UNKNOWN


def _eval_sequence(elts: list[ast.expr], kind: type) -> object:
    values = [_eval_pure(item) for item in elts]
    if _UNKNOWN in values:
        return _UNKNOWN
    return kind(values)


def _apply_bin(op: ast.operator, left: object, right: object) -> object:
    if isinstance(op, ast.Add):
        return left + right
    if isinstance(op, ast.Sub):
        return left - right
    if isinstance(op, ast.Mult):
        return left * right
    if isinstance(op, ast.Div):
        return left / right
    if isinstance(op, ast.FloorDiv):
        return left // right
    if isinstance(op, ast.Mod):
        return left % right
    return left ** right


def _apply_cmp(op: ast.cmpop, left: object, right: object) -> bool:
    if isinstance(op, ast.Eq):
        return left == right
    if isinstance(op, ast.NotEq):
        return left != right
    if isinstance(op, ast.Lt):
        return left < right
    if isinstance(op, ast.LtE):
        return left <= right
    if isinstance(op, ast.Gt):
        return left > right
    if isinstance(op, ast.GtE):
        return left >= right
    if isinstance(op, ast.Is):
        return left is right
    if isinstance(op, ast.IsNot):
        return left is not right
    if isinstance(op, ast.In):
        return left in right
    if isinstance(op, ast.NotIn):
        return left not in right
    raise TypeError(op)


def _local_modules(work_dir: Path) -> set[str]:
    names: set[str] = set()
    if not work_dir.is_dir():
        return names
    for path in work_dir.glob("*.py"):
        names.add(path.stem)
    for path in work_dir.iterdir():
        if path.is_dir() and any(path.glob("*.py")):
            names.add(path.name)
    return names
