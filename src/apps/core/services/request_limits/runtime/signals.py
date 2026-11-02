"""What Smart limiting reacts to, measured in this process: per-scope request count, 5xx count, 429 count and p95
latency in fixed windows of ``controller.window_seconds``, plus the in-flight requests (sampled at every admission)
against the concurrency limit, and the tier-aware admission control over those slots.

Everything is in memory under one lock per structure; nothing is written anywhere per request.
"""

import math
import random
import threading
from dataclasses import dataclass, field

from ..rules.controller import ScopeSignal, Snapshot
from ..rules.limits import admission_limit
from .context import section

# Reservoir sampling only needs to be unbiased, not unpredictable.
_RANDOM = random.Random()  # nosec B311


def percentile(samples: list[float], share: float = 0.95) -> float | None:
    if not samples:
        return None
    ordered = sorted(samples)
    return ordered[max(0, math.ceil(share * len(ordered)) - 1)]


@dataclass
class _ScopeWindow:
    requests: int = 0
    errors: int = 0
    limited: int = 0
    seen: int = 0
    samples: list = field(default_factory=list)

    def sample(self, latency_ms: float, keep: int) -> None:
        self.seen += 1
        if len(self.samples) < keep:
            self.samples.append(latency_ms)
            return
        slot = _RANDOM.randrange(self.seen)
        if slot < keep:
            self.samples[slot] = latency_ms


class _Window:
    def __init__(self):
        self.lock = threading.Lock()
        self.started = None
        self._clear()

    def _clear(self):
        self.scopes: dict[str, _ScopeWindow] = {}
        self.inflight_total = 0.0
        self.inflight_samples = 0
        self.refused = 0

    def reset(self, now: float | None = None) -> None:
        with self.lock:
            self.started = now
            self._clear()


WINDOW = _Window()


class _InFlight:
    def __init__(self):
        self.lock = threading.Lock()
        self.count = 0


INFLIGHT = _InFlight()


def admit(tier: str, now: float) -> bool:
    """Take one concurrency slot for a ``tier`` request; False when the tier is at its share."""
    admission = section("admission")
    slots = admission["concurrency_limit"]
    limit = admission_limit(tier, slots, section("tiers"), admission["p0_reserved_slots"])
    with INFLIGHT.lock:
        admitted = INFLIGHT.count < limit
        if admitted:
            INFLIGHT.count += 1
        in_use = INFLIGHT.count
    with WINDOW.lock:
        if WINDOW.started is None:
            WINDOW.started = now
        WINDOW.inflight_total += min(1.0, in_use / slots)
        WINDOW.inflight_samples += 1
        WINDOW.refused += 0 if admitted else 1
    return admitted


def release() -> None:
    with INFLIGHT.lock:
        INFLIGHT.count = max(0, INFLIGHT.count - 1)


def in_flight() -> int:
    return INFLIGHT.count


def record(scope: str, status: int, latency_ms: float, now: float, *, served: bool = True) -> None:
    """Count one finished request. One this limiter refused (``served=False``) counts only as limited: its instant
    answer would dilute the latency and request counts the controller reads."""
    keep = section("controller")["max_latency_samples"]
    with WINDOW.lock:
        if WINDOW.started is None:
            WINDOW.started = now
        stats = WINDOW.scopes.setdefault(scope, _ScopeWindow())
        if not served:
            stats.limited += 1
            return
        stats.requests += 1
        stats.errors += 1 if status >= 500 else 0
        stats.limited += 1 if status == 429 else 0
        stats.sample(latency_ms, keep)


def take_if_due(now: float) -> Snapshot | None:
    """The window that ended, once (to the first caller after it ends), and a fresh window; else None."""
    with WINDOW.lock:
        if WINDOW.started is None or now - WINDOW.started < section("controller")["window_seconds"]:
            return None
        scopes, started = WINDOW.scopes, WINDOW.started
        inflight = WINDOW.inflight_total / WINDOW.inflight_samples if WINDOW.inflight_samples else 0.0
        refused = WINDOW.refused
        WINDOW.started = now
        WINDOW._clear()
    every_sample = [sample for stats in scopes.values() for sample in stats.samples]
    return Snapshot(
        started=started,
        ended=now,
        scopes={
            name: ScopeSignal(stats.requests, stats.errors, stats.limited, percentile(stats.samples))
            for name, stats in scopes.items()
        },
        requests=sum(stats.requests for stats in scopes.values()),
        errors=sum(stats.errors for stats in scopes.values()),
        p95_ms=percentile(every_sample),
        inflight_share=inflight,
        refused=refused,
    )
