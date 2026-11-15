from __future__ import annotations

import ast
import io
import tokenize
from collections.abc import Iterator
from dataclasses import dataclass

from .config import Profile

NON_CODE_TOKENS = {
    tokenize.COMMENT,
    tokenize.NL,
    tokenize.NEWLINE,
    tokenize.INDENT,
    tokenize.DEDENT,
    tokenize.ENCODING,
    tokenize.ENDMARKER,
}


BLOCK_NODES = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.TryStar, ast.With, ast.AsyncWith, ast.Match)


SCOPE_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)


@dataclass(frozen=True)
class Finding:
    metric: str
    path: str
    symbol: str
    value: int
    advisory: int
    hard: int

    @property
    def key(self) -> str:
        return f"{self.metric}:{self.path}::{self.symbol}" if self.symbol else f"{self.metric}:{self.path}"

    @property
    def is_hard(self) -> bool:
        return self.value > self.hard

    def describe(self) -> str:
        level = "HARD" if self.is_hard else "advisory"
        where = f"{self.path}::{self.symbol}" if self.symbol else self.path
        return f"[{level}] {self.metric} {self.value} (advisory>{self.advisory}, hard>{self.hard})  {where}"


def docstring_lines(tree: ast.AST) -> set[int]:
    lines: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        body = node.body
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            if isinstance(body[0].value.value, str):
                lines.update(range(body[0].lineno, (body[0].end_lineno or body[0].lineno) + 1))
    return lines


def code_lines(source: str, tree: ast.AST) -> set[int]:
    """Physical line numbers that carry code (see module docstring)."""
    skip = docstring_lines(tree)
    lines: set[int] = set()
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type in NON_CODE_TOKENS:
            continue
        for line in range(token.start[0], token.end[0] + 1):
            if line not in skip:
                lines.add(line)
    return lines


def _child_blocks(node: ast.AST) -> Iterator[tuple[ast.AST, int]]:
    """Yield (child, depth increment) pairs, flattening ``elif`` chains."""
    for name, value in ast.iter_fields(node):
        children = value if isinstance(value, list) else [value]
        for child in children:
            if not isinstance(child, ast.AST):
                continue
            if isinstance(node, ast.If) and name == "orelse" and len(value) == 1 and isinstance(child, ast.If):
                yield child, 0
            else:
                yield child, 1 if isinstance(child, BLOCK_NODES) else 0


def max_nesting(function: ast.AST) -> int:
    deepest = 0
    stack: list[tuple[ast.AST, int]] = [(child, inc) for child, inc in _child_blocks(function)]
    while stack:
        node, depth = stack.pop()
        if isinstance(node, SCOPE_NODES):
            continue
        deepest = max(deepest, depth)
        for child, inc in _child_blocks(node):
            stack.append((child, depth + inc))
    return deepest


def iter_functions(tree: ast.AST) -> Iterator[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]]:
    def visit(node: ast.AST, prefix: str) -> Iterator[tuple[str, ast.AST]]:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                name = f"{prefix}{child.name}"
                yield name, child
                yield from visit(child, f"{name}.")
            elif isinstance(child, ast.ClassDef):
                yield from visit(child, f"{prefix}{child.name}.")
            else:
                yield from visit(child, prefix)

    yield from visit(tree, "")


def _check(metric: str, rel: str, symbol: str, value: int, limits: tuple[int, int] | None) -> Iterator[Finding]:
    if limits and value > limits[0]:
        yield Finding(metric, rel, symbol, value, limits[0], limits[1])


def analyze_source(rel: str, source: str, profile: Profile) -> list[Finding]:
    tree = ast.parse(source)
    lines = code_lines(source, tree)
    findings = list(_check("file-lines", rel, "", len(lines), profile.file_lines))
    for name, function in iter_functions(tree):
        end = function.end_lineno or function.lineno
        length = sum(1 for line in lines if function.lineno <= line <= end)
        findings.extend(_check("function-lines", rel, name, length, profile.function_lines))
        findings.extend(_check("nesting", rel, name, max_nesting(function), profile.nesting))
    return findings
