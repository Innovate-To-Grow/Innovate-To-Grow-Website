"""Which job kinds the worker leaves unclaimed for now: those whose delivery lane would only defer them."""

import logging

from apps.core.services.delivery_rates.families import lane_gated

from .registry import registered_job_kinds

logger = logging.getLogger(__name__)


def blocked_job_kinds(now=None) -> frozenset[str]:
    """Kinds whose delivery family and lane are paced, cooling down or stopped (``delivery_rates.lane_gated``).

    The gates are hints read without a lock; a failure to read them blocks nothing, since admission still decides.
    """
    lanes: dict[tuple[str, str], list[str]] = {}
    for name, kind in registered_job_kinds().items():
        if kind.family is not None:
            lanes.setdefault((kind.family, kind.lane), []).append(name)
    blocked: set[str] = set()
    for (family, lane), names in lanes.items():
        try:
            gated = lane_gated(family, lane, now)
        except Exception:  # noqa: BLE001 - a hint that cannot be read must not stop the worker claiming.
            logger.exception("Could not read the %s %s delivery gate", family, lane)
            gated = False
        if gated:
            blocked.update(names)
    return frozenset(blocked)
