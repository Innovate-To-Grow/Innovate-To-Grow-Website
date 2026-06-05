"""Auth + configuration commands: configure, login, logout, whoami."""

import typer

from .. import auth, config, runtime
from ..errors import CliError

configure_app = typer.Typer(help="Manage CLI configuration (base URL, profiles).")


def register(app: typer.Typer) -> None:
    app.add_typer(configure_app, name="configure")
    app.command()(login)
    app.command()(logout)
    app.command()(whoami)


# --- configure (AWS-style get/set/list, plus a bare default for back-compat) ---
@configure_app.callback(invoke_without_command=True)
def configure(
    ctx: typer.Context,
    base_url: str | None = typer.Option(None, "--base-url", help="Persist the backend base URL for the profile."),
) -> None:
    """Persist configuration. With no subcommand, sets the base URL for the active profile.

    ``--base-url`` defaults to the environment / .env value when omitted.
    """
    if ctx.invoked_subcommand is not None:
        return

    def run():
        url = base_url or config.default_base_url()
        config.set_base_url(url, profile=runtime.current_profile())
        typer.echo(f"Configured base URL: {url}")

    runtime._execute(run)


@configure_app.command("set")
def configure_set(key: str, value: str) -> None:
    """Set a configuration value (currently: ``base_url``)."""

    def run():
        if key != "base_url":
            raise CliError(f"Unknown config key {key!r}. Supported: base_url.")
        config.set_base_url(value, profile=runtime.current_profile())
        typer.echo(f"Configured base URL: {value}")

    runtime._execute(run)


@configure_app.command("get")
def configure_get(key: str) -> None:
    """Print a configuration value (currently: ``base_url``)."""

    def run():
        if key != "base_url":
            raise CliError(f"Unknown config key {key!r}. Supported: base_url.")
        typer.echo(config.current_base_url(runtime.current_profile()))

    runtime._execute(run)


@configure_app.command("list")
def configure_list() -> None:
    """List known profiles and the active default."""

    def run():
        return {
            "default_profile": config.default_profile(),
            "profiles": config.list_profiles(),
        }

    runtime._execute(run)


# --- login / logout / whoami ----------------------------------------------
def login() -> None:
    """Open the browser to the admin login and cache a short-lived bearer token."""

    def run():
        profile = runtime.current_profile()
        base_url = config.current_base_url(profile)
        auth.login(base_url, profile=profile)
        typer.echo(f"Logged in to {base_url}. Token cached.")

    runtime._execute(run)


def logout() -> None:
    """Clear the locally cached token for the active profile."""
    if config.clear_credentials(runtime.current_profile()):
        typer.echo("Logged out; local token cleared.")
    else:
        typer.echo("No cached credentials to clear.")


def whoami(as_json: bool = typer.Option(False, "--json", help="Emit JSON.")) -> None:
    """Show the authenticated member and token expiry."""
    runtime._execute(lambda: runtime._client().get("/admin-api/whoami/"), as_json=as_json)
