"""Client-side result projection (the ``--query`` seam).

U1 shipped a no-op passthrough so the ``emit`` pipeline had a stable shape. U3
replaces :func:`run_query` with a JMESPath implementation and maps expression
errors to :class:`~i2g_admin.errors.CliError`. No other unit imports or edits
this module.
"""

from typing import Any

import jmespath
from jmespath.exceptions import JMESPathError

from .errors import CliError


def run_query(data: Any, expression: str | None) -> Any:
    """Return ``data`` projected through the JMESPath ``expression``.

    An empty or ``None`` expression is a passthrough (the data is returned
    unchanged). Any parse or evaluation error raised by JMESPath is mapped to a
    user-facing :class:`~i2g_admin.errors.CliError`.
    """
    if not expression:
        return data
    try:
        return jmespath.search(expression, data)
    except JMESPathError as exc:
        raise CliError(f"Invalid --query expression: {exc}") from exc
