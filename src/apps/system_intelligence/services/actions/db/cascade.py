"""Backwards-compatible shim. Logic now lives in core's shared safe-ORM layer.

See ``apps.core.services.db_tools.safe_orm.cascade``.
"""

# Re-imported so the dotted patch target
# ``apps.system_intelligence.services.actions.db.cascade.Collector.collect``
# (test_actions_coverage) keeps resolving even though the implementation moved.
from django.db.models.deletion import Collector  # noqa: F401

from apps.core.services.db_tools.safe_orm.cascade import cascade_summary, collect_cascade_impact

__all__ = [
    "cascade_summary",
    "collect_cascade_impact",
]
