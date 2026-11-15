"""The action engine's errors. ``ActionRequestError`` lives in core's shared safe-ORM layer (this module re-exports it)
so the CLI admin API and the AI action engine raise the same type.

See ``apps.core.services.db_tools.safe_orm.exceptions``.
"""

from apps.core.services.db_tools.safe_orm.exceptions import ActionRequestError


class ActionRefused(ActionRequestError):
    """A change the approver may not make: a rule, not a fault. A proposal is refused with it; at approval the request
    fails with its message, which is fixed text naming the rule, shown to the approver as it is."""


__all__ = ["ActionRefused", "ActionRequestError"]
