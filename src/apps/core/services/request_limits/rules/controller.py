"""The Smart limit controller: priority-ordered AIMD over per-scope factors. Pure.

Each closed signal window is assessed once:

- **overload** (in-flight share, admission refusals, p95 latency or 5xx share at or above its overload threshold):
  the lowest-priority tier that still has room is cut — every active (traffic in the window), sheddable scope of
  P3 is multiplied by P3's ``decrease_factor``; once all of P3 is at its floor (or idle) P2 is cut, then P1. P0 and
  fixed scopes are never cut for load.
- **healthy** (every signal below its healthy threshold): the highest-priority tier still below full is restored
  by its ``recovery_step`` — P1 first, then P2, then P3 — but not a scope cut within ``recovery_hold_seconds``.
- otherwise **steady**: nothing changes.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field

from .limits import RECOVERY_ORDER, SHED_ORDER, ScopeConfig, smart_factor

OVERLOAD = "overload"
HEALTHY = "healthy"
STEADY = "steady"
EPSILON = 1e-6


@dataclass(frozen=True)
class ScopeSignal:
    requests: int = 0
    errors: int = 0
    limited: int = 0
    p95_ms: float | None = None


@dataclass(frozen=True)
class Snapshot:
    """One process's closed signal window."""

    started: float
    ended: float
    scopes: dict = field(default_factory=dict)
    requests: int = 0
    errors: int = 0
    p95_ms: float | None = None
    # Mean share of the concurrency slots in use, sampled at every admission.
    inflight_share: float = 0.0
    # Requests refused for lack of a slot of their tier.
    refused: int = 0

    def active(self, scope: str) -> bool:
        """The scope had traffic in the window, served or refused: a tier whose requests are already being refused
        is still shed to its floor before the next tier is touched."""
        signal = self.scopes.get(scope)
        return bool(signal and (signal.requests or signal.limited))


@dataclass(frozen=True)
class Pressure:
    level: str
    reasons: tuple = ()
    values: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Plan:
    # "shed", "restore" or "hold".
    action: str
    tier: str | None = None
    factors: dict = field(default_factory=dict)


def assess(snapshot: Snapshot, controller: dict) -> Pressure:
    """Is the process overloaded, healthy or in between, and why."""
    enough = snapshot.requests >= controller["min_requests"]
    error_share = snapshot.errors / snapshot.requests if snapshot.requests else 0.0
    p95 = snapshot.p95_ms if enough else None
    values = {
        "requests": snapshot.requests,
        "error_share": round(error_share, 4),
        "p95_ms": None if p95 is None else round(p95, 1),
        "inflight_share": round(snapshot.inflight_share, 4),
        "refused": snapshot.refused,
    }
    reasons = []
    if snapshot.inflight_share >= controller["inflight_overload_share"]:
        reasons.append(f"{snapshot.inflight_share:.0%} of request slots in use")
    if snapshot.refused:
        reasons.append(f"{snapshot.refused} requests refused for lack of a slot")
    if enough and error_share >= controller["error_overload_share"]:
        reasons.append(f"{error_share:.1%} server errors")
    if p95 is not None and p95 >= controller["latency_overload_ms"]:
        reasons.append(f"p95 response time {p95:.0f} ms")
    if reasons:
        return Pressure(OVERLOAD, tuple(reasons), values)
    calm = snapshot.inflight_share < controller["inflight_healthy_share"]
    if enough:
        calm = calm and error_share < controller["error_healthy_share"]
        calm = calm and (p95 is None or p95 < controller["latency_healthy_ms"])
    return Pressure(HEALTHY if calm else STEADY, (), values)


def _shed(configs, snapshot, tiers) -> Plan:
    for tier in SHED_ORDER:
        candidates = [
            config
            for config in configs
            if config.tier == tier
            and config.sheddable
            and snapshot.active(config.scope)
            and smart_factor(config) > config.floor + EPSILON
        ]
        if candidates:
            decrease = tiers[tier]["decrease_factor"]
            factors = {config.scope: max(config.floor, smart_factor(config) * decrease) for config in candidates}
            return Plan("shed", tier, factors)
    return Plan("hold")


def _restored(factor: float) -> float:
    # Float steps (0.1 + 0.1 + ...) land a hair below 1; full is full.
    return 1.0 if factor >= 1 - EPSILON else factor


def _restore(configs, tiers, now, hold_seconds) -> Plan:
    for tier in RECOVERY_ORDER:
        below = [
            config for config in configs if config.tier == tier and config.sheddable and config.factor < 1 - EPSILON
        ]
        if not below:
            continue
        # Strict order: a lower tier waits until this one is fully restored, even while this one is on hold.
        ready = [config for config in below if config.last_cut_at is None or now - config.last_cut_at >= hold_seconds]
        step = tiers[tier]["recovery_step"]
        factors = {config.scope: _restored(smart_factor(config) + step) for config in ready}
        return Plan("restore", tier, factors) if factors else Plan("hold", tier)
    return Plan("hold")


def plan(pressure: Pressure, configs: Iterable[ScopeConfig], snapshot: Snapshot, tiers: dict, *, now, hold_seconds):
    """The factor changes ``pressure`` calls for."""
    configs = list(configs)
    if pressure.level == OVERLOAD:
        return _shed(configs, snapshot, tiers)
    if pressure.level == HEALTHY:
        return _restore(configs, tiers, now, hold_seconds)
    return Plan("hold")
