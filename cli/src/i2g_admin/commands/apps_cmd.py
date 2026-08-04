"""Introspection command: apps."""

import typer

from .. import runtime
from ..errors import CliError


def register(app: typer.Typer) -> None:
    app.command(name="apps")(apps_cmd)


def apps_cmd(as_json: bool = typer.Option(False, "--json", help="Emit JSON.")) -> None:
    """List the Django apps reachable through the admin API."""

    def fetch_visible_apps():
        client = runtime._client()
        identity = client.get("/admin-api/whoami/")
        rows = client.get("/admin-api/apps/")
        if not isinstance(identity, dict) or not isinstance(rows, list):
            raise CliError("The admin API returned an invalid apps response.")
        if identity.get("is_superuser"):
            return rows
        allowed = set(identity.get("admin_apps") or [])
        return [row for row in rows if isinstance(row, dict) and row.get("app_label") in allowed]

    runtime._execute(fetch_visible_apps, as_json=as_json)
