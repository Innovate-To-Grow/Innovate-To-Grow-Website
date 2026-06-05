"""The output pipeline: project (``--query``) then format (``--output``).

``emit`` is the frozen public entrypoint. Two disjoint seams hang off it:
- :func:`i2g_admin.query.run_query` — the ``--query`` projection (U3 fills it).
- the formatter registry in :mod:`i2g_admin.formatters` — ``--output`` (U2 fills text/yaml/csv).

The legacy ``as_json`` keyword is preserved for back-compat: when true it forces
the ``json`` formatter regardless of ``output``.
"""

import typer

from .formatters import get_formatter
from .query import run_query


def emit(data, *, as_json: bool = False, output: str | None = None, query: str | None = None) -> None:
    projected = run_query(data, query)
    fmt = "json" if as_json else (output or "table")
    rendered = get_formatter(fmt)(projected)
    if rendered is not None:
        typer.echo(rendered)
