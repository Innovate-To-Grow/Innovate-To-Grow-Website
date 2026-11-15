from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


SRC = ROOT / "src"


SKIP_PARTS = {"tests", "migrations", "__pycache__"}


@dataclass(frozen=True)
class Import:
    source: str
    target: str
    line: int
    top_level: bool


def module_name(path: Path) -> str:
    parts = list(path.relative_to(SRC).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def iter_modules() -> Iterator[tuple[str, Path]]:
    for path in sorted((SRC / "apps").rglob("*.py")):
        if SKIP_PARTS.isdisjoint(path.relative_to(SRC).parts):
            yield module_name(path), path


def _is_type_checking(node: ast.If) -> bool:
    test = node.test
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def _walk_imports(body: list[ast.stmt], top_level: bool) -> Iterator[tuple[ast.stmt, bool]]:
    """Yield import statements, marking those that run at module import time."""
    for node in body:
        if isinstance(node, ast.Import | ast.ImportFrom):
            yield node, top_level
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            yield from _walk_imports(node.body, False)
        elif isinstance(node, ast.If) and _is_type_checking(node):
            yield from _walk_imports(node.body, False)
            yield from _walk_imports(node.orelse, top_level)
        else:
            # Class bodies and if/try/with/for blocks run at import time.
            for field in ("body", "orelse", "finalbody"):
                yield from _walk_imports(getattr(node, field, None) or [], top_level)
            for clause in [*getattr(node, "handlers", []), *getattr(node, "cases", [])]:
                yield from _walk_imports(clause.body, top_level)


def _resolve_relative(module: str, is_package: bool, level: int, target: str | None) -> str:
    base = module.split(".") if is_package else module.split(".")[:-1]
    if level > 1:
        base = base[: -(level - 1)]
    return ".".join([*base, target] if target else base)


def resolve_imports(module: str, path: Path, known: set[str]) -> list[Import]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    is_package = path.name == "__init__.py"
    found: list[Import] = []
    for node, top_level in _walk_imports(tree.body, True):
        if isinstance(node, ast.Import):
            targets = [alias.name for alias in node.names]
        else:
            base = _resolve_relative(module, is_package, node.level, node.module) if node.level else (node.module or "")
            # `from pkg import sub` imports the submodule when one exists.
            targets = [f"{base}.{alias.name}" if f"{base}.{alias.name}" in known else base for alias in node.names]
        for target in dict.fromkeys(targets):
            if target.startswith("apps."):
                found.append(Import(module, _deepest_known(target, known), node.lineno, top_level))
    return found


def _deepest_known(target: str, known: set[str]) -> str:
    parts = target.split(".")
    while parts and ".".join(parts) not in known:
        parts.pop()
    return ".".join(parts) or target


def collect() -> list[Import]:
    modules = dict(iter_modules())
    known = set(modules)
    imports: list[Import] = []
    for module, path in modules.items():
        imports.extend(resolve_imports(module, path, known))
    return imports
