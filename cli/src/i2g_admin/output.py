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
    """Project ``data`` through ``query``, then render it in the chosen format.

    Format selection has a deliberate precedence that this function pins down:

    1. ``as_json=True`` (the per-command ``--json`` flag) is an explicit alias
       for ``--output json`` and **wins over** ``output``. This is intentional,
       not a bug: ``--output yaml records list --json`` emits JSON, because the
       narrower per-command flag is treated as the stronger expression of intent.
       The two knobs are kept as separate mechanisms only for back-compat — the
       per-command ``--json`` predates the global ``--output`` and every command
       still accepts it.
    2. Otherwise ``output`` selects the formatter (``yaml``, ``csv``, ``text``,
       ``json``, ``table``).
    3. With neither set, the default is the rich ``table`` renderer.

    An unknown ``output`` value surfaces a :class:`~i2g_admin.errors.CliError`
    from :func:`~i2g_admin.formatters.get_formatter`.

    .. warning::
       Do not "simplify" the ``fmt`` ternary by flipping the operand order or
       swapping ``as_json`` for ``output`` — that would silently invert the
       documented precedence. ``test_output.py`` guards each branch.
    """
    projected = run_query(data, query)
    fmt = "json" if as_json else (output or "table")
    rendered = get_formatter(fmt)(projected)
    if rendered is not None:
        typer.echo(rendered)
