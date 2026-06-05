"""Client-side result projection (the ``--query`` seam).

U1 ships a no-op passthrough so the ``emit`` pipeline has a stable shape. U3
replaces :func:`run_query` with a JMESPath implementation (adding the jmespath
dependency) and maps expression errors to :class:`~i2g_admin.errors.CliError`.
No other unit imports or edits this module.
"""

from typing import Any


def run_query(data: Any, expression: str | None) -> Any:
    """Return ``data`` projected through ``expression``.

    Until U3 lands, any non-empty expression is reported as unsupported rather
    than silently ignored, so users are never misled into thinking a filter ran.
    """
    if not expression:
        return data
    from .errors import CliError

    raise CliError("--query is not available in this build yet.")
