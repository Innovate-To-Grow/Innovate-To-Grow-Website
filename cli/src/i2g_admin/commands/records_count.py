"""``records count`` — count matching records without fetching rows.

Calls the list endpoint with ``count=1`` (plus any ``--filter``s) so the backend
returns only ``{model, count}`` via ``queryset.count()``.
"""

import typer

from .. import runtime
from .query_params import filter_params


def register(records_app: typer.Typer) -> None:
    records_app.command("count")(records_count)


def records_count(
    app_label: str,
    model_name: str,
    filter_: list[str] = typer.Option(None, "--filter", help="key=value (repeatable)."),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Count records matching optional filters (no rows are fetched)."""
    params = filter_params(filter_)
    params.append(("count", "1"))
    path = f"/admin-api/records/{app_label}/{model_name}/"
    runtime._execute(lambda: runtime._client().get(path, params=params), as_json=as_json)
