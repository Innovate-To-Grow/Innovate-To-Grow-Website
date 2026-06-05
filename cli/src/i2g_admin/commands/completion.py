"""Shell completion command (AWS-CLI-style ``completion show <shell>``).

``i2g-admin completion show bash`` prints a completion script to stdout that you
can ``eval`` or write to your shell's completion directory. For a one-step
install, prefer the built-in ``i2g-admin --install-completion``.
"""

import typer
from click.shell_completion import get_completion_class

from .. import runtime
from ..errors import CliError

# AWS-CLI-style supported shells. We validate against this fixed set rather than
# the global Click registry alone, because Typer mutates that registry (adding
# powershell/pwsh) as a side effect of building the command — which would make
# the accepted set order-dependent. bash/zsh/fish is the documented surface.
SUPPORTED_SHELLS = ("bash", "zsh", "fish")

completion_app = typer.Typer(
    help=(
        "Print shell completion scripts (bash, zsh, fish).\n\n"
        "For a one-step install, use the built-in: i2g-admin --install-completion"
    ),
    no_args_is_help=True,
)


def register(app: typer.Typer) -> None:
    app.add_typer(completion_app, name="completion")
    completion_app.command("show")(completion_show)


def completion_show(shell: str = typer.Argument(..., help="Shell to target: bash, zsh, or fish.")) -> None:
    """Print the completion script for SHELL to stdout."""

    def run():
        if shell not in SUPPORTED_SHELLS:
            raise CliError(f"Unsupported shell {shell!r}. Use bash, zsh, or fish.")
        # Runtime import: the app module is fully loaded by the time this runs,
        # and importing it at module load would create an app<->commands cycle.
        from ..app import app as typer_app

        cli = typer.main.get_command(typer_app)
        comp_cls = get_completion_class(shell)
        typer.echo(comp_cls(cli, {}, "i2g-admin", "_I2G_ADMIN_COMPLETE").source())

    runtime._execute(run)
