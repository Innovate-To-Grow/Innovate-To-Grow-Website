"""GCRA pacing (the virtual-scheduling form of a token bucket), with the bulk lane and cooldowns.

Each identity keeps a theoretical arrival time ``tat``. A request may be sent at ``max(now, tat − τ)``, after which
``tat`` moves to ``max(tat, slot) + increment``. ``τ = tolerance × interval`` allows that many requests back to
back; ``policy.effective_rate`` clips it so the steady rate plus the burst never exceeds the provider limit in any
window. Campaigns also keep their own ``tat_bulk`` paced at ``bulk_share`` of the rate.

A cooldown counts as if ``tat`` were ``cooldown_until + τ``: nothing is sent before it ends, and the requests that
waited go out one interval apart instead of in a burst.
"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from .policy import EffectiveRate


@dataclass(frozen=True)
class Slot:
    at: datetime
    tat: datetime
    tat_bulk: datetime | None
    # Seconds this request moves the channel's tat (and the bulk lane's).
    increment: float
    bulk_increment: float | None


def increment_seconds(rate: EffectiveRate, pace_cost: float = 1, parts: int | None = None) -> float:
    """How far one request moves ``tat``: its cost at the rate, or for SMS its parts at the parts rate when longer.

    ``inc = max(cost / r_msg, parts / r_parts)``.
    """
    increment = pace_cost / rate.per_second
    if parts and rate.parts_rate:
        increment = max(increment, parts / rate.parts_rate)
    return increment


def tolerance_seconds(rate: EffectiveRate) -> float:
    """τ: the burst allowance in seconds, measured in single (one-part) requests."""
    interval = 1 / rate.per_second
    if rate.parts_rate:
        interval = max(interval, 1 / rate.parts_rate)
    return rate.tolerance * interval


def _up(seconds: float) -> timedelta:
    # Datetimes hold whole microseconds. Rounding every increment up and the tolerance down keeps the window bound
    # strict: with the burst clipped to ⌊B⌋ − rate, the last request of a full window lands exactly on its edge.
    return timedelta(microseconds=math.ceil(seconds * 1_000_000))


def _down(seconds: float) -> timedelta:
    return timedelta(microseconds=math.floor(seconds * 1_000_000))


def _later(*values: datetime | None) -> datetime:
    return max(value for value in values if value is not None)


def next_slot(
    *,
    now: datetime,
    tat: datetime | None,
    tat_bulk: datetime | None,
    cooldown_until: datetime | None,
    increment: float,
    tolerance: float,
    bulk_share: float | None = None,
) -> Slot:
    """The earliest slot for one request and the ``tat`` values after taking it. ``bulk_share`` is given for a
    campaign request only. Pure: the caller decides whether to take the slot or defer."""
    tau = _down(tolerance)
    after_cooldown = cooldown_until + tau if cooldown_until is not None else None
    channel_tat = _later(tat, now, after_cooldown)
    at = max(now, channel_tat - tau)
    new_bulk = bulk_increment = None
    if bulk_share is not None:
        bulk_tau = _down(tolerance / bulk_share)
        bulk_increment = increment / bulk_share
        lane_tat = _later(tat_bulk, now, cooldown_until + bulk_tau if cooldown_until is not None else None)
        at = max(at, lane_tat - bulk_tau)
        new_bulk = max(lane_tat, at) + _up(bulk_increment)
    new_tat = max(channel_tat, at) + _up(increment)
    return Slot(at=at, tat=new_tat, tat_bulk=new_bulk, increment=increment, bulk_increment=bulk_increment)
