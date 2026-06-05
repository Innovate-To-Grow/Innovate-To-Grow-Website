"""Generic record CRUD: records list/get/create/update/delete.

Wave-2 units extend this module at well-defined seams:
- U4 fills the ``# U4`` anchor inside ``records_list`` (auto-pagination).
- U7 adds options at the ``# U7`` anchors on ``records_create`` / ``records_update``.
- U8 / U11 each append one ``register`` line at their numbered anchor below.
"""

import typer

from .. import runtime

records_app = typer.Typer(help="Generic CRUD over /admin-api/ records.", no_args_is_help=True)


def register(app: typer.Typer) -> None:
    app.add_typer(records_app, name="records")
    records_app.command("list")(records_list)
    records_app.command("get")(records_get)
    records_app.command("create")(records_create)
    records_app.command("update")(records_update)
    records_app.command("delete")(records_delete)
    # --- wave-2 record subcommands (one line each, on their own line) ---
    from . import records_wait  # U8

    records_wait.register(records_app)
    # U11: from . import records_count; records_count.register(records_app)


def records_list(
    app_label: str,
    model_name: str,
    filter_: list[str] = typer.Option(None, "--filter", help="key=value (repeatable)."),
    order: list[str] = typer.Option(None, "--order", help="field or -field (repeatable)."),
    field: list[str] = typer.Option(None, "--field", help="Restrict columns (repeatable)."),
    limit: int | None = typer.Option(None, "--limit"),
    offset: int | None = typer.Option(None, "--offset"),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
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
    path = f"/admin-api/records/{app_label}/{model_name}/"
    # U4: auto-pagination hook — replace the single GET below with paginate(...).
    runtime._execute(lambda: runtime._client().get(path, params=params), as_json=as_json)


def records_get(app_label: str, model_name: str, pk: str, as_json: bool = typer.Option(False, "--json")) -> None:
    """Fetch one record by primary key."""
    runtime._execute(
        lambda: runtime._client().get(f"/admin-api/records/{app_label}/{model_name}/{pk}/"), as_json=as_json
    )


def records_create(
    app_label: str,
    model_name: str,
    data: str = typer.Option(..., "--data", help="Inline JSON, @file, or @- for stdin."),
    # U7: --generate-cli-skeleton / --cli-input-json options go here.
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Create a record from a JSON payload."""

    def run():
        payload = runtime._load_data(data)
        return runtime._client().post(f"/admin-api/records/{app_label}/{model_name}/", json_body=payload)

    runtime._execute(run, as_json=as_json)


def records_update(
    app_label: str,
    model_name: str,
    pk: str,
    data: str = typer.Option(..., "--data", help="Inline JSON, @file, or @- for stdin."),
    # U7: --generate-cli-skeleton / --cli-input-json options go here.
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Update a record from a JSON payload."""

    def run():
        payload = runtime._load_data(data)
        return runtime._client().patch(f"/admin-api/records/{app_label}/{model_name}/{pk}/", json_body=payload)

    runtime._execute(run, as_json=as_json)


def records_delete(
    app_label: str,
    model_name: str,
    pk: str,
    confirm_cascade: bool = typer.Option(False, "--confirm-cascade", help="Allow cascading deletes."),
    yes: bool = typer.Option(False, "--yes", help="Skip the interactive confirmation."),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Delete a record (interactive confirmation unless --yes)."""
    if not yes:
        typer.confirm(f"Delete {app_label}.{model_name} '{pk}'?", abort=True)
    params = {"confirm_cascade": "true"} if confirm_cascade else None
    runtime._execute(
        lambda: runtime._client().delete(f"/admin-api/records/{app_label}/{model_name}/{pk}/", params=params),
        as_json=as_json,
    )
