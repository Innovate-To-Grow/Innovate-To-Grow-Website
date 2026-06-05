"""Introspection commands: models, schema."""

import typer

from .. import runtime


def register(app: typer.Typer) -> None:
    app.command()(models)
    app.command()(schema)


def models(as_json: bool = typer.Option(False, "--json", help="Emit JSON.")) -> None:
    """List the models readable/writable through the admin API."""
    runtime._execute(lambda: runtime._client().get("/admin-api/models/"), as_json=as_json)


def schema(app_label: str, model_name: str, as_json: bool = typer.Option(False, "--json", help="Emit JSON.")) -> None:
    """Show readable/writable fields for one model."""
    runtime._execute(
        lambda: runtime._client().get(f"/admin-api/models/{app_label}/{model_name}/schema/"), as_json=as_json
    )
