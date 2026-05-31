import json
import sys
from pathlib import Path

import typer

from . import auth, config
from .client import ApiClient
from .errors import CliError
from .output import emit

app = typer.Typer(help="Remote record management for the Innovate-To-Grow backend.", no_args_is_help=True)
records_app = typer.Typer(help="Generic CRUD over /admin-api/ records.", no_args_is_help=True)
app.add_typer(records_app, name="records")


def _client() -> ApiClient:
    base_url, token = auth.ensure_token()
    return ApiClient(base_url, token)


def _execute(action, *, as_json: bool = False) -> None:
    try:
        result = action()
    except CliError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    if result is not None:
        emit(result, as_json=as_json)


def _load_data(value: str):
    if value == "@-":
        raw = sys.stdin.read()
    elif value.startswith("@"):
        try:
            raw = Path(value[1:]).read_text()
        except OSError as exc:
            raise CliError(f"Could not read data file {value[1:]!r}: {exc}") from exc
    else:
        raw = value
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CliError(f"--data is not valid JSON: {exc}") from exc


@app.command()
def configure(base_url: str | None = typer.Option(None, "--base-url", help="Backend base URL.")):
    """Persist the backend base URL (default: the production API)."""

    def run():
        url = base_url or config.default_base_url()
        config.set_base_url(url)
        typer.echo(f"Configured base URL: {url}")

    _execute(run)


@app.command()
def login():
    """Open the browser to the admin login and cache a short-lived bearer token."""

    def run():
        base_url = config.current_base_url()
        auth.login(base_url)
        typer.echo(f"Logged in to {base_url}. Token cached.")

    _execute(run)


@app.command()
def logout():
    """Clear the locally cached token."""
    if config.clear_credentials():
        typer.echo("Logged out; local token cleared.")
    else:
        typer.echo("No cached credentials to clear.")


@app.command()
def whoami(as_json: bool = typer.Option(False, "--json", help="Emit JSON.")):
    """Show the authenticated member and token expiry."""
    _execute(lambda: _client().get("/admin-api/whoami/"), as_json=as_json)


@app.command()
def models(as_json: bool = typer.Option(False, "--json", help="Emit JSON.")):
    """List the models readable/writable through the admin API."""
    _execute(lambda: _client().get("/admin-api/models/"), as_json=as_json)


@app.command()
def schema(app_label: str, model_name: str, as_json: bool = typer.Option(False, "--json", help="Emit JSON.")):
    """Show readable/writable fields for one model."""
    _execute(lambda: _client().get(f"/admin-api/models/{app_label}/{model_name}/schema/"), as_json=as_json)


@records_app.command("list")
def records_list(
    app_label: str,
    model_name: str,
    filter_: list[str] = typer.Option(None, "--filter", help="key=value (repeatable)."),
    order: list[str] = typer.Option(None, "--order", help="field or -field (repeatable)."),
    field: list[str] = typer.Option(None, "--field", help="Restrict columns (repeatable)."),
    limit: int | None = typer.Option(None, "--limit"),
    offset: int | None = typer.Option(None, "--offset"),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON."),
):
    """List records with optional filters, ordering, field selection, and paging."""
    params = []
    for item in filter_ or []:
        params.append(("filter", item))
    for item in order or []:
        params.append(("order", item))
    for item in field or []:
        params.append(("field", item))
    if limit is not None:
        params.append(("limit", str(limit)))
    if offset is not None:
        params.append(("offset", str(offset)))
    _execute(lambda: _client().get(f"/admin-api/records/{app_label}/{model_name}/", params=params), as_json=as_json)


@records_app.command("get")
def records_get(app_label: str, model_name: str, pk: str, as_json: bool = typer.Option(False, "--json")):
    """Fetch one record by primary key."""
    _execute(lambda: _client().get(f"/admin-api/records/{app_label}/{model_name}/{pk}/"), as_json=as_json)


@records_app.command("create")
def records_create(
    app_label: str,
    model_name: str,
    data: str = typer.Option(..., "--data", help="Inline JSON, @file, or @- for stdin."),
    as_json: bool = typer.Option(False, "--json"),
):
    """Create a record from a JSON payload."""

    def run():
        payload = _load_data(data)
        return _client().post(f"/admin-api/records/{app_label}/{model_name}/", json_body=payload)

    _execute(run, as_json=as_json)


@records_app.command("update")
def records_update(
    app_label: str,
    model_name: str,
    pk: str,
    data: str = typer.Option(..., "--data", help="Inline JSON, @file, or @- for stdin."),
    as_json: bool = typer.Option(False, "--json"),
):
    """Update a record from a JSON payload."""

    def run():
        payload = _load_data(data)
        return _client().patch(f"/admin-api/records/{app_label}/{model_name}/{pk}/", json_body=payload)

    _execute(run, as_json=as_json)


@records_app.command("delete")
def records_delete(
    app_label: str,
    model_name: str,
    pk: str,
    confirm_cascade: bool = typer.Option(False, "--confirm-cascade", help="Allow cascading deletes."),
    yes: bool = typer.Option(False, "--yes", help="Skip the interactive confirmation."),
    as_json: bool = typer.Option(False, "--json"),
):
    """Delete a record (interactive confirmation unless --yes)."""
    if not yes:
        typer.confirm(f"Delete {app_label}.{model_name} '{pk}'?", abort=True)
    params = {"confirm_cascade": "true"} if confirm_cascade else None
    _execute(
        lambda: _client().delete(f"/admin-api/records/{app_label}/{model_name}/{pk}/", params=params),
        as_json=as_json,
    )
