"""Runtime glue shared by every command module.

This is a *leaf* module: it imports the data/auth/output layers but never
``commands`` or ``app``. Command modules import the glue from here, so adding a
new command module (or a test that imports one directly) can never create the
``app`` <-> ``commands`` import cycle.

Tests monkeypatch these symbols on ``i2g_admin.runtime`` (e.g. ``runtime._client``);
``app`` re-exports them for back-compat callers.
"""

import json
import sys
from pathlib import Path

import click
import typer

from . import auth, config  # noqa: F401  (auth/config re-exported for command modules + tests)
from .client import ApiClient
from .context import Context, build_client
from .errors import CliError
from .output import emit


def _current_context() -> Context | None:
    """Return the active :class:`Context`, or None when invoked outside a command."""
    cctx = click.get_current_context(silent=True)
    obj = getattr(cctx, "obj", None) if cctx is not None else None
    return obj if isinstance(obj, Context) else None


def current_profile() -> str | None:
    """The ``--profile`` selected for this invocation, or None outside a command."""
    context = _current_context()
    return context.profile if context else None


def _client() -> ApiClient:
    """Build an :class:`ApiClient` for the active profile / global options.

    With no active CLI context (e.g. direct unit-test calls) it falls back to the
    legacy zero-argument token lookup so existing tests and call sites keep working.
    """
    context = _current_context()
    if context is None:
        base_url, token = auth.ensure_token()
        return ApiClient(base_url, token)
    return build_client(context)


def _execute(action, *, as_json: bool = False) -> None:
    context = _current_context()
    try:
        result = action()
        if result is not None:
            emit(
                result,
                as_json=as_json,
                output=(context.output if context else None),
                query=(context.query if context else None),
            )
    except CliError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        if context and context.debug:
            typer.secho(repr(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc


def _load_data(value: str):
    if value == "@-":
        raw = sys.stdin.read()
    elif value.startswith("@"):
        filename = value[1:]
        if not filename:
            raise CliError("--data @<file> requires a filename (got a bare '@').")
        try:
            raw = Path(filename).read_text()
        except OSError as exc:
            raise CliError(f"Could not read data file {filename!r}: {exc}") from exc
    else:
        raw = value
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CliError(f"--data is not valid JSON: {exc}") from exc
