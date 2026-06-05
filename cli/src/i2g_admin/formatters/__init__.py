"""Output-format registry (the ``--output`` seam).

A formatter takes the (already query-projected) data and renders it. It either
returns a string for the caller to ``echo``, or prints directly and returns
``None`` (the ``table`` formatter does the latter, via rich).

U1 ships ``json`` and ``table``. The ``text``/``yaml``/``csv`` keys are
registered as stubs in :mod:`i2g_admin.formatters.stubs`; U2 fills their bodies.
Wave-2 units that add a format only touch ``stubs.py`` — never this module.
"""

import json as jsonlib
from collections.abc import Callable
from typing import Any

from rich.console import Console
from rich.table import Table

from ..errors import CliError

console = Console()

# name -> formatter(data) -> str | None
REGISTRY: dict[str, Callable[[Any], str | None]] = {}


def register(name: str) -> Callable[[Callable[[Any], str | None]], Callable[[Any], str | None]]:
    """Decorator registering a formatter under ``name`` (replacing any existing entry)."""

    def decorate(fn: Callable[[Any], str | None]) -> Callable[[Any], str | None]:
        REGISTRY[name] = fn
        return fn

    return decorate


def available_formats() -> list[str]:
    return sorted(REGISTRY)


def get_formatter(name: str) -> Callable[[Any], str | None]:
    try:
        return REGISTRY[name]
    except KeyError:
        raise CliError(f"Unknown output format {name!r}. Available: {', '.join(available_formats())}.") from None


# --- built-in formatters (json + table) ------------------------------------
@register("json")
def _format_json(data: Any) -> str:
    return jsonlib.dumps(data, indent=2, default=str)


@register("table")
def _format_table(data: Any) -> None:
    """Render with rich; prints directly and returns None (preserves legacy behavior)."""
    if isinstance(data, list):
        _render_list(data)
    elif isinstance(data, dict):
        _render_dict(data)
    else:
        console.print(str(data))
    return None


def _render_list(rows) -> None:
    if not rows:
        console.print("(no results)")
        return
    if all(isinstance(row, dict) for row in rows):
        columns = list(dict.fromkeys(key for row in rows for key in row))
        table = Table(*columns)
        for row in rows:
            table.add_row(*[str(row.get(column, "")) for column in columns])
        console.print(table)
        return
    for row in rows:
        console.print(str(row))


def _render_dict(data) -> None:
    table = Table("field", "value")
    for key, value in data.items():
        table.add_row(str(key), str(value))
    console.print(table)


# Registering the text/yaml/csv stub keys. Importing for the side effect keeps
# this module the single source of the registry while U2 owns only stubs.py.
from . import stubs  # noqa: E402,F401
