"""Backwards-compatible shim. Logic now lives in core's shared safe-ORM layer.

See ``apps.core.services.db_tools.safe_orm.records``.
"""

from apps.core.services.db_tools.safe_orm.records import (
    assert_snapshot_unchanged,
    check_model_permission,
    clone_model_instance,
    get_object,
    record_repr,
    serialize_model_instance,
)

__all__ = [
    "assert_snapshot_unchanged",
    "check_model_permission",
    "clone_model_instance",
    "get_object",
    "record_repr",
    "serialize_model_instance",
]
