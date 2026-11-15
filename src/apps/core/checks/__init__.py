"""System checks for settings that must hold before the site starts.

Every management command runs them, including the startup commands in ``docker/runtime/entrypoint.sh`` and the background worker,
so a production task whose key store is not Secrets Manager stops before it serves a request.

Importing this package registers every check (``AppConfig.ready``): ``credential_store``, ``microsoft_graph`` and
``request_limits``.
"""

from .credential_store import check_credential_store
from .microsoft_graph import check_microsoft_graph
from .request_limits import (
    REQUEST_LIMIT_MIDDLEWARE,
    REQUEST_LIMIT_PREDECESSORS,
    REQUEST_LIMIT_SUCCESSORS,
    check_request_limits,
)

__all__ = [
    "REQUEST_LIMIT_MIDDLEWARE",
    "REQUEST_LIMIT_PREDECESSORS",
    "REQUEST_LIMIT_SUCCESSORS",
    "check_credential_store",
    "check_microsoft_graph",
    "check_request_limits",
]
