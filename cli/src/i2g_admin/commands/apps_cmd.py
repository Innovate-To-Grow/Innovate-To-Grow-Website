"""Introspection command: apps."""

import typer

from .. import runtime


def register(app: typer.Typer) -> None:
    app.command(name="apps")(apps_cmd)


def apps_cmd(as_json: bool = typer.Option(False, "--json", help="Emit JSON.")) -> None:
    """List the Django apps reachable through the admin API."""
    runtime._execute(lambda: runtime._client().get("/admin-api/apps/"), as_json=as_json)
