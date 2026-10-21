#!/usr/bin/env python3
"""Enforce Django-app dependency directions and forbid import-time module cycles.

Rules live in ``scripts/ci/python_dependencies.toml``; the policy is explained in
docs/architecture/code-quality.md.

* **Boundaries.** Each module under ``src/apps/<app>/`` may import another app
  only when ``<app>`` lists it in ``[allowed]``. Modules matching a
  ``composition`` pattern (project-wide management commands, ``AppConfig``
  registration) may import any app. Every other cross-app import needs an
  ``[[exceptions]]`` entry with a reason.
* **Cycles.** Module-level imports (not those inside a function body or an
  ``if TYPE_CHECKING:`` block) form the import-time graph. Any strongly
  connected component with more than one module is a cycle; known cycles are
  listed in ``[[cycles]]`` and anything new fails.

Tests and migrations are not scanned. Stale exceptions and stale cycle entries
fail too, so both lists can only shrink.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import sys
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
CONFIG_PATH = ROOT / "scripts" / "ci" / "python_dependencies.toml"
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


def app_of(module: str) -> str:
    return module.split(".")[1] if module.count(".") >= 1 else module


def load_config(path: Path = CONFIG_PATH) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def boundary_violations(imports: list[Import], config: dict) -> list[Import]:
    allowed: dict[str, list[str]] = config["allowed"]
    composition: list[str] = config.get("composition", [])
    violations = []
    for item in imports:
        source_app = app_of(item.source)
        if source_app == app_of(item.target) or _is_allowed(item.target, allowed.get(source_app, [])):
            continue
        if any(fnmatch.fnmatchcase(item.source, pattern) for pattern in composition):
            continue
        violations.append(item)
    return violations


def _is_allowed(target: str, entries: list[str]) -> bool:
    """An entry is an app label (``authn``) or a public module path inside it (``mail.services.tokens``)."""
    return any(target == f"apps.{entry}" or target.startswith(f"apps.{entry}.") for entry in entries)


def exception_matches(item: Import, entry: dict) -> bool:
    return fnmatch.fnmatchcase(item.source, entry["from"]) and (
        item.target == entry["to"] or item.target.startswith(entry["to"] + ".")
    )


class _Tarjan:
    """Iterative Tarjan's algorithm: a recursive one would overflow on a long import chain."""

    def __init__(self, graph: dict[str, set[str]]):
        self.graph = graph
        self.index: dict[str, int] = {}
        self.low: dict[str, int] = {}
        self.on_stack: set[str] = set()
        self.stack: list[str] = []
        self.components: list[list[str]] = []

    def _visit(self, node: str) -> Iterator[str]:
        self.index[node] = self.low[node] = len(self.index)
        self.stack.append(node)
        self.on_stack.add(node)
        return iter(sorted(self.graph.get(node, ())))

    def _pop_component(self, node: str) -> None:
        component = []
        while True:
            member = self.stack.pop()
            self.on_stack.discard(member)
            component.append(member)
            if member == node:
                break
        if len(component) > 1:
            self.components.append(sorted(component))

    def _next_unvisited(self, node: str, children: Iterator[str]) -> str | None:
        """Advance ``node``'s child iterator to the next unvisited child, updating lowlinks on the way."""
        for child in children:
            if child not in self.index:
                return child
            if child in self.on_stack:
                self.low[node] = min(self.low[node], self.index[child])
        return None

    def run(self, root: str) -> None:
        work = [(root, self._visit(root))]
        while work:
            node, children = work[-1]
            child = self._next_unvisited(node, children)
            if child is not None:
                work.append((child, self._visit(child)))
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                self.low[parent] = min(self.low[parent], self.low[node])
            if self.low[node] == self.index[node]:
                self._pop_component(node)


def strongly_connected(graph: dict[str, set[str]]) -> list[list[str]]:
    """Strongly connected components with more than one node, each sorted, in sorted order."""
    tarjan = _Tarjan(graph)
    for root in sorted(graph):
        if root not in tarjan.index:
            tarjan.run(root)
    return sorted(tarjan.components)


def collect() -> list[Import]:
    modules = dict(iter_modules())
    known = set(modules)
    imports: list[Import] = []
    for module, path in modules.items():
        imports.extend(resolve_imports(module, path, known))
    return imports


def import_cycles(imports: list[Import]) -> list[list[str]]:
    graph: dict[str, set[str]] = {}
    for item in imports:
        if item.top_level and item.target != item.source:
            graph.setdefault(item.source, set()).add(item.target)
            graph.setdefault(item.target, set())
    return strongly_connected(graph)


def _boundary_errors(imports: list[Import], config: dict) -> list[str]:
    """Unexcepted boundary violations, and exceptions that no longer match anything."""
    errors: list[str] = []
    exceptions = config.get("exceptions", [])
    used_exceptions: set[int] = set()
    for item in boundary_violations(imports, config):
        matched = [i for i, entry in enumerate(exceptions) if exception_matches(item, entry)]
        if matched:
            used_exceptions.update(matched)
            continue
        errors.append(
            f"boundary: {item.source} (line {item.line}) imports {item.target}; "
            f"`{app_of(item.source)}` may import only {config['allowed'].get(app_of(item.source), [])}"
        )
    errors.extend(
        f"stale boundary exception: {entry['from']} -> {entry['to']}"
        for i, entry in enumerate(exceptions)
        if i not in used_exceptions
    )
    return errors


def _cycle_errors(found_cycles: set[tuple[str, ...]], config: dict) -> list[str]:
    known_cycles = {tuple(sorted(entry["modules"])) for entry in config.get("cycles", [])}
    errors = ["new import cycle: " + " -> ".join(component) for component in sorted(found_cycles - known_cycles)]
    errors.extend(
        "stale cycle entry (cycle is gone, remove it): " + ", ".join(component)
        for component in sorted(known_cycles - found_cycles)
    )
    return errors


def _print_graph(imports: list[Import]) -> None:
    counts: dict[tuple[str, str], int] = {}
    for item in imports:
        pair = (app_of(item.source), app_of(item.target))
        if pair[0] != pair[1]:
            counts[pair] = counts.get(pair, 0) + 1
    for (source, target), count in sorted(counts.items()):
        print(f"  {source:20} -> {target:20} {count}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--graph", action="store_true", help="print the app-level import counts")
    args = parser.parse_args(argv)

    config = load_config()
    imports = collect()
    found_cycles = {tuple(component) for component in import_cycles(imports)}
    errors = _boundary_errors(imports, config) + _cycle_errors(found_cycles, config)
    if args.graph:
        _print_graph(imports)

    cross_app = sum(1 for item in imports if app_of(item.source) != app_of(item.target))
    print(
        f"Python dependencies: {len(imports)} imports ({cross_app} cross-app), "
        f"{len(config.get('exceptions', []))} boundary exceptions, {len(found_cycles)} known import cycles"
    )
    for error in errors:
        print(f"ERROR: {error}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
