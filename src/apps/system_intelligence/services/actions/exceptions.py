"""Backwards-compatible shim. ``ActionRequestError`` now lives in core's shared
safe-ORM layer so the CLI admin API and the AI action engine raise the same type.

See ``apps.core.services.db_tools.safe_orm.exceptions``.
"""

from apps.core.services.db_tools.safe_orm.exceptions import ActionRequestError

__all__ = ["ActionRequestError"]
