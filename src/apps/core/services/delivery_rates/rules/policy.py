"""The precedence rule between Smart rate, the manual rate and the provider limits. ``effective_rate`` is its only
implementation: the limiter, the status lines and the send estimates all call it.

::

    bound B = min(operator provider_limit, documented ceiling, last-known reported limit)   # those that exist
              else the channel's fallback_rate ("limit unknown")
    Smart on : rate = B × headroom × factor(now)          # the manual rate is never read
    Smart off: rate = manual rate, capped at the provider limits (never at the fallback)
    Both     : burst k = min(burst − 1, ⌊B⌋ − rate), so rate·W + k never exceeds the bound in a window W
    SMS      : the same for message parts per second (MPS); Smart scales both, the manual rate only the messages

"Last-known" is the most recent successful provider read for the identity, whatever its age: a failed refresh
keeps it. Settings ceilings apply here too, so lowering one with ``DELIVERY_RATES_OVERRIDES`` caps stored rows.
"""

import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .controller import MANUAL, SMART, current_factor
from .defaults import RateSpec


class BoundSource(StrEnum):
    REPORTED = "reported"
    OPERATOR = "operator"
    DOCUMENTED = "documented"
    FALLBACK = "fallback"


@dataclass(frozen=True)
class Bound:
    """A provider limit in the channel's unit, and where it comes from."""

    value: float
    source: BoundSource

    @property
    def known(self) -> bool:
        return self.source != BoundSource.FALLBACK


@dataclass(frozen=True)
class EffectiveRate:
    mode: str
    # In the channel's unit (per ``window`` seconds).
    rate: float
    window: int
    bound: Bound
    # Smart rate's factor (None while Smart rate is off).
    factor: float | None
    # Requests that may go back to back beyond the steady rate.
    tolerance: float
    # Smart rate off and the manual rate is above a provider limit, which applies instead.
    manual_capped: bool = False
    # SMS only: the message parts bound and rate, per second.
    parts: Bound | None = None
    parts_rate: float | None = None

    @property
    def per_second(self) -> float:
        return self.rate / self.window

    @property
    def smart(self) -> bool:
        return self.mode == SMART


def _positive(value) -> float | None:
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) and number > 0 else None


def _smallest(candidates) -> Bound | None:
    present = [Bound(value, source) for value, source in candidates if value is not None]
    # min() keeps the first of equal values: a reported limit wins a tie (the most informative source), then the
    # documented one, so a seeded policy field still equal to its documented value is not labelled "operator".
    return min(present, key=lambda bound: bound.value) if present else None


def rate_bound(policy, state, spec: RateSpec) -> Bound:
    hard = _smallest(
        (
            (_positive(state.discovered_rate), BoundSource.REPORTED),
            (_positive(spec.provider_limit), BoundSource.DOCUMENTED),
            (_positive(policy.provider_limit), BoundSource.OPERATOR),
        )
    )
    return hard or Bound(float(spec.fallback_rate), BoundSource.FALLBACK)


def parts_bound(policy, state, spec: RateSpec) -> Bound | None:
    if not spec.has_parts:
        return None
    hard = _smallest(
        (
            (_positive(state.discovered_parts_rate), BoundSource.REPORTED),
            (_positive(spec.parts_limit), BoundSource.DOCUMENTED),
            (_positive(policy.parts_limit), BoundSource.OPERATOR),
        )
    )
    return hard or Bound(float(spec.parts_fallback_rate), BoundSource.FALLBACK)


def _tolerance(spec: RateSpec, bound: float, rate: float) -> float:
    # ⌊B⌋: a window holds whole requests, so a fractional limit (14.5/sec) allows 14 in any one second.
    return max(0.0, min(spec.burst - 1, math.floor(bound) - rate))


def smart_rate(policy, state, spec: RateSpec, now: datetime) -> float:
    """What Smart rate runs at (or would run at, while it is off), in the channel's unit."""
    bound = rate_bound(policy, state, spec)
    return bound.value * spec.headroom * current_factor(state, spec, now, limit_known=bound.known)


def effective_rate(policy, state, spec: RateSpec, now: datetime) -> EffectiveRate:
    """The rate one identity runs at now. Pure: it reads ``policy``, ``state`` and ``spec`` and changes nothing."""
    bound = rate_bound(policy, state, spec)
    parts = parts_bound(policy, state, spec)
    capped = False
    if policy.smart_enabled:
        factor = current_factor(state, spec, now, limit_known=bound.known)
        rate = bound.value * spec.headroom * factor
        parts_rate = parts.value * spec.headroom * factor if parts else None
        mode = SMART
    else:
        factor = None
        rate = float(policy.manual_rate)
        # clean() keeps the manual rate within the operator's and the documented limit, so this only bites when
        # the provider reports less, or a deployer lowered a ceiling below a stored row. The fallback is a guess
        # and never caps an operator's choice.
        if bound.known and rate > bound.value:
            rate, capped = bound.value, True
        parts_rate = parts.value if parts else None
        mode = MANUAL
    tolerance = _tolerance(spec, bound.value, rate)
    if parts and parts_rate:
        tolerance = min(tolerance, _tolerance(spec, parts.value, parts_rate))
    return EffectiveRate(
        mode=mode,
        rate=rate,
        window=spec.window,
        bound=bound,
        factor=factor,
        tolerance=tolerance,
        manual_capped=capped,
        parts=parts,
        parts_rate=parts_rate,
    )
