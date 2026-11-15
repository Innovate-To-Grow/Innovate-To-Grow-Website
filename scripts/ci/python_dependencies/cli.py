#!/usr/bin/env python3
"""Enforce Django-app dependency directions and forbid import-time module cycles.

Rules live in ``scripts/ci/python_dependencies/python_dependencies.toml``; the policy is explained in
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

from .cycles import import_cycles
from .imports import Import, collect
from .rules import app_of, boundary_violations, exception_matches, load_config


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
