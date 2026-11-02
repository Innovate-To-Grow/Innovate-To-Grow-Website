"""The precedence rule between Smart limit and the manual limit, and the slots each tier may take. Pure: these read
their arguments only, so the middleware, the admin and the tests share one implementation.

::

    baseline B = the scope's REQUEST_RATE_LIMITS ``requests``, capped by the per-caller ceiling
    Smart on : f = 1 for P0 and fixed scopes, else clamp(factor, smart floor, 1)
               per caller = max(1, ⌊B × f⌋), everyone together = max(1, ⌊global cap × f⌋)   # manual never read
               per source (callers without a verified identity) = max(1, ⌊source cap × f⌋)
    Smart off: per caller = min(manual, ceiling), everyone together = global cap, per source = source cap
    Per-process counters (no shared store): each limit ÷ live processes, rounded up (never 0)
"""

import math
from dataclasses import dataclass, replace

P0 = "p0"
SHED_ORDER = ("p3", "p2", "p1")
RECOVERY_ORDER = ("p1", "p2", "p3")


@dataclass(frozen=True)
class ScopeConfig:
    """One scope as the limiter uses it: the settings baseline, the policy row and the Smart state together."""

    scope: str
    label: str
    tier: str
    identity: str
    baseline: int
    manual: int
    period: int
    smart: bool
    floor: float
    fixed: bool
    enabled: bool
    ceiling: int | None
    global_cap: int | None
    # The per-source flood ceiling (``source_cap``), or None.
    source_cap: int | None = None
    factor: float = 1.0
    # Epoch seconds, or None.
    factor_changed_at: float | None = None
    last_cut_at: float | None = None

    @property
    def sheddable(self) -> bool:
        """Smart may tighten it for load: Smart on, not P0, not fixed."""
        return self.smart and self.tier != P0 and not self.fixed


@dataclass(frozen=True)
class Limits:
    mode: str
    # Requests per ``period`` seconds for one caller, and for everyone together (None: no aggregate cap).
    per_identity: int
    global_cap: int | None
    period: int
    # The Smart factor applied (None while Smart is off).
    factor: float | None
    # Requests per ``period`` from one source without a verified identity (None: no flood ceiling).
    source_cap: int | None = None


def _clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def smart_factor(config: ScopeConfig) -> float:
    """The share of the baseline Smart limit allows now."""
    if config.tier == P0 or config.fixed:
        return 1.0
    return _clamp(config.factor, min(config.floor, 1.0), 1.0)


def _per_process(limit: int | None, processes: int) -> int | None:
    if limit is None or processes <= 1:
        return limit
    return max(1, math.ceil(limit / processes))


def _scaled(limit: int | None, factor: float) -> int | None:
    return max(1, math.floor(limit * factor + 1e-9)) if limit else None


def effective_limits(config: ScopeConfig, processes: int = 1) -> Limits:
    """The limits one request of ``config``'s scope is held to in a process that is one of ``processes``."""
    if config.smart:
        factor = smart_factor(config)
        baseline = min(config.baseline, config.ceiling) if config.ceiling else config.baseline
        per_identity = _scaled(baseline, factor)
        global_cap, source_cap = _scaled(config.global_cap, factor), _scaled(config.source_cap, factor)
        mode = "smart"
    else:
        factor = None
        per_identity = min(config.manual, config.ceiling) if config.ceiling else config.manual
        global_cap, source_cap = config.global_cap, config.source_cap
        mode = "manual"
    return Limits(
        mode=mode,
        per_identity=_per_process(per_identity, processes),
        global_cap=_per_process(global_cap, processes),
        period=config.period,
        factor=factor,
        source_cap=_per_process(source_cap, processes),
    )


def strike_limits(config: ScopeConfig, processes: int = 1) -> Limits:
    """The limits a caller must exceed for a refusal to count as its own doing (an abuse strike): the scope's limits
    at full size. A cut Smart made for load is not the caller's fault, so going over only the cut is no strike."""
    return effective_limits(replace(config, factor=1.0), processes)


def admission_limit(tier: str, concurrency: int, tiers: dict, reserved: int) -> int:
    """How many requests in flight (all tiers together) a process may already hold and still admit one of ``tier``.

    P0 may use every slot. Any other tier stops at its share of the slots and always leaves ``reserved`` to P0;
    at least one slot stays open to it, so a tiny concurrency limit still serves every tier.
    """
    if tier == P0:
        return concurrency
    share = math.floor(concurrency * tiers[tier]["admission_share"] + 1e-9)
    return max(1, min(share, concurrency - reserved))
