"""The precedence rule between Smart rate, the manual rate and the provider limits. ``effective_rate`` is its only
implementation: the limiter, the status lines and the send estimates all call it.

::

    bound B = min(operator provider_limit, documented ceiling, last-known reported limit)   # those that exist
              else the channel's fallback_rate ("limit unknown")
    ceiling P = ⌊B⌋ when B ≥ 1 (a window holds whole requests), else B
    Smart on : rate = min(B × headroom × factor(now), P)          # the manual rate is never read
    Smart off: rate = manual rate, capped at P when B is a provider limit (never at the fallback)
    Both     : burst k = min(burst − 1, ⌊B⌋ − rate), so rate·W + k never exceeds ⌊B⌋ in a window W
    SMS      : the same for message parts per second (MPS); Smart scales both, the manual rate only the messages

A window holds whole requests, so under a bound of at least one per window the pace never exceeds ⌊B⌋: a 14.5/sec
limit allows 14 in any one second (pacing at 14.5 would let 15 into some second).

"Last-known" is the most recent successful provider read for the identity, whatever its age: a failed refresh
keeps it. Settings ceilings apply here too, so lowering one with ``DELIVERY_RATES_OVERRIDES`` caps stored rows. A
provider limit migration 0036 carried over from the old campaign send rate (``provider_limit_carried_over``) counts
only until the provider reports a limit for the identity.
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
    # The previous release's campaign send rate, standing in until the provider reports its limit.
    CARRIED_OVER = "carried_over"
    DOCUMENTED = "documented"
    # The limit entered on the provider configuration (Microsoft Graph's mailbox limits from OIT).
    TENANT = "tenant"
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


def _operator_limit(policy, reported: float | None) -> tuple[float | None, BoundSource]:
    """The policy's provider limit and its source. One carried over from the old campaign send rate stands in only
    until the provider reports a limit, which then replaces it (it is not an operator cap)."""
    value = _positive(policy.provider_limit)
    if policy.provider_limit_carried_over:
        return (value if reported is None else None), BoundSource.CARRIED_OVER
    return value, BoundSource.OPERATOR


def rate_bound(policy, state, spec: RateSpec) -> Bound:
    reported = _positive(state.discovered_rate)
    ceiling_source = BoundSource.TENANT if spec.tenant_limits else BoundSource.DOCUMENTED
    hard = _smallest(
        (
            (reported, BoundSource.REPORTED),
            (_positive(spec.provider_limit), ceiling_source),
            _operator_limit(policy, reported),
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


def pace_ceiling(bound: float) -> float:
    """The fastest pace a bound allows: ⌊B⌋ per window, since a window holds whole requests (B itself below one)."""
    return float(math.floor(bound)) if bound >= 1 else bound


def _tolerance(spec: RateSpec, bound: float, rate: float) -> float:
    # ⌊B⌋: a window holds whole requests, so a fractional limit (14.5/sec) allows 14 in any one second.
    return max(0.0, min(spec.burst - 1, math.floor(bound) - rate))


def smart_rate(policy, state, spec: RateSpec, now: datetime) -> float:
    """What Smart rate runs at (or would run at, while it is off), in the channel's unit."""
    bound = rate_bound(policy, state, spec)
    rate = bound.value * spec.headroom * current_factor(state, spec, now, limit_known=bound.known)
    return min(rate, pace_ceiling(bound.value))


def effective_rate(policy, state, spec: RateSpec, now: datetime) -> EffectiveRate:
    """The rate one identity runs at now. Pure: it reads ``policy``, ``state`` and ``spec`` and changes nothing."""
    bound = rate_bound(policy, state, spec)
    parts = parts_bound(policy, state, spec)
    capped = False
    if policy.smart_enabled:
        factor = current_factor(state, spec, now, limit_known=bound.known)
        rate = min(bound.value * spec.headroom * factor, pace_ceiling(bound.value))
        parts_rate = min(parts.value * spec.headroom * factor, pace_ceiling(parts.value)) if parts else None
        mode = SMART
    else:
        factor = None
        rate = float(policy.manual_rate)
        # clean() keeps the manual rate within the operator's and the documented limit, so this only bites when
        # the provider reports less, a deployer lowered a ceiling below a stored row, or the limit is fractional
        # (whole requests per window). The fallback is a guess and never caps an operator's choice.
        if bound.known and rate > pace_ceiling(bound.value):
            rate, capped = pace_ceiling(bound.value), True
        parts_rate = pace_ceiling(parts.value) if parts else None
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
