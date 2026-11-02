"""The channel and identity each delivery family (email, SMS) uses right now, for the code that only knows the
family: the background worker's claim-time gates, the inline batch sizes and the maintenance limit reads.

A family's sender registers a resolver by dotted path (imported on first use, so ``core`` imports no app that
owns one). It returns the active ``(channel, identity)``, or None while the family is not configured.
"""

import logging
import math
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.utils.module_loading import import_string

from apps.core.models import DeliveryRatePolicy, DeliveryRateState

from .rules.channels import Family, Lane
from .rules.defaults import rate_spec, section
from .rules.policy import effective_rate
from .runtime import context

logger = logging.getLogger(__name__)

_RESOLVERS: dict[Family, str] = {}
_gate_cache: dict[Family, tuple[float, tuple]] = {}
_gate_lock = threading.Lock()


@dataclass(frozen=True)
class Target:
    channel: str
    identity: str


def register_family(family: str, resolver: str) -> None:
    """Register the dotted path of ``() -> (channel, identity) | None`` for ``family``."""
    _RESOLVERS[Family(family)] = resolver


def registered_families() -> tuple[Family, ...]:
    return tuple(_RESOLVERS)


def active_target(family: str) -> Target | None:
    """The family's active channel and identity, or None (not configured, or its configuration is broken)."""
    path = _RESOLVERS.get(Family(family))
    if path is None:
        return None
    try:
        found = import_string(path)()
    except Exception:  # noqa: BLE001 - a broken configuration fails its sends, never the worker or a page.
        logger.warning("The active %s delivery channel could not be resolved", family, exc_info=True)
        return None
    return Target(*found) if found else None


def clear_gate_cache() -> None:
    with _gate_lock:
        _gate_cache.clear()


def _gates(family: Family) -> tuple[datetime | None, datetime | None]:
    """``(all_gate_until, bulk_gate_until)`` of the family's active identity, read without a lock."""
    with _gate_lock:
        cached = _gate_cache.get(family)
    if cached is not None and cached[0] > time.monotonic():
        return cached[1]
    target = active_target(family)
    row = None
    if target is not None:
        rows = DeliveryRateState.objects.filter(channel=target.channel, identity=target.identity)
        row = rows.values_list("all_gate_until", "bulk_gate_until").first()
    gates = tuple(row) if row else (None, None)
    with _gate_lock:
        _gate_cache[family] = (time.monotonic() + section("jobs")["gate_cache_seconds"], gates)
    return gates


def lane_gated(family: str, lane: str, now: datetime | None = None) -> bool:
    """True while a worker claiming a job of this family and lane would only be deferred.

    The gates are hints the limiter leaves on the identity's state: campaigns can next be admitted at
    ``bulk_gate_until``, and nothing is sent before ``all_gate_until`` (a transactional job may claim that long
    before it, as it waits for its slot up to the worker's wait).
    """
    now = now or context.clock()
    all_gate, bulk_gate = _gates(Family(family))
    if Lane(lane) == Lane.BULK:
        return any(gate is not None and now < gate for gate in (all_gate, bulk_gate))
    lead = timedelta(seconds=context.wait_cap(context.WaitMode.WORKER))
    return all_gate is not None and now < all_gate - lead


def inline_batch_limit(family: str) -> int | None:
    """How many messages one request may send inline at the family's current transactional rate.

    Enough for ``waits.inline_request_budget_seconds`` of sending: the burst, then one per interval. None when the
    family has no active channel (nothing would be sent anyway).
    """
    target = active_target(family)
    if target is None:
        return None
    policy = DeliveryRatePolicy.for_channel(target.channel)
    state = DeliveryRateState.objects.filter(channel=target.channel, identity=target.identity).first()
    state = state or DeliveryRateState(channel=target.channel, identity=target.identity)
    rate = effective_rate(policy, state, rate_spec(target.channel), context.clock())
    budget = section("waits")["inline_request_budget_seconds"]
    return max(1, math.floor(1 + rate.tolerance + budget * rate.per_second))
