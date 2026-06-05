import typer

from . import __version__, auth, config  # noqa: F401  (re-exported for back-compat + tests)
from .commands import register
from .context import Context

# Re-export the runtime glue so callers/tests can patch i2g_admin.app._client etc.
# The real definitions live in the leaf `runtime` module to avoid an app<->commands cycle.
from .runtime import (  # noqa: F401
    _client,
    _execute,
    _load_data,
)

app = typer.Typer(help="Remote record management for the Innovate-To-Grow backend.", no_args_is_help=True)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"i2g-admin {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    profile: str | None = typer.Option(
        None, "--profile", envvar=config.ENV_PROFILE, help="Named config/credentials profile."
    ),
    output: str = typer.Option("table", "--output", help="Output format: table, json (text/yaml/csv when available)."),
    query: str | None = typer.Option(None, "--query", help="Client-side JMESPath projection of the result."),
    no_paginate: bool = typer.Option(False, "--no-paginate", help="Disable automatic pagination."),
    max_items: int | None = typer.Option(None, "--max-items", help="Stop after this many items when paginating."),
    page_size: int | None = typer.Option(None, "--page-size", help="Items to request per page when paginating."),
    max_attempts: int = typer.Option(1, "--max-attempts", help="Max HTTP attempts (retry transient failures)."),
    connect_timeout: float = typer.Option(5.0, "--connect-timeout", help="Per-request connect timeout (seconds)."),
    read_timeout: float = typer.Option(30.0, "--read-timeout", help="Per-request read timeout (seconds)."),
    debug: bool = typer.Option(False, "--debug", help="Emit debug detail on errors."),
    version: bool = typer.Option(
        None, "--version", callback=_version_callback, is_eager=True, help="Show the version and exit."
    ),
) -> None:
    """Populate the shared :class:`Context` from the global options."""
    # Validate --max-items here, at the boundary, so it is rejected uniformly on
    # every path. `records list --limit/--offset N` honors an explicit page with a
    # single request and never reaches paginate()'s own guard, so a per-path check
    # there would silently accept a negative value on the explicit-page route.
    if max_items is not None and max_items < 0:
        typer.secho("--max-items must be >= 0.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    ctx.obj = Context(
        profile=profile,
        output=output,
        query=query,
        no_paginate=no_paginate,
        max_items=max_items,
        page_size=page_size,
        max_attempts=max_attempts,
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
        debug=debug,
    )


register(app)
