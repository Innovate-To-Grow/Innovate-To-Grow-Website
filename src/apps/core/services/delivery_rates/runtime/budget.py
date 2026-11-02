"""Daily (rolling 24 h) and Graph hourly (rolling 1 h) budgets, counted in ``DeliveryUsageBucket`` rows.

A limit is the smallest of the operator's value, the provider-reported one, the documented ceiling in the settings
and (SMTP) the host profile. Mail may use ``budget_headroom`` of it; campaigns stop at ``1 − transactional_reserve``
of that, so login codes and tickets keep the rest. Usage is the sum of the buckets that overlap the window; an over
budget request is deferred until enough of it ages out.
"""

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from django.db.models import F, Q, Sum
from django.db.models.functions import Greatest

from apps.core.models import DeliveryUsageBucket

from ..rules.channels import Lane, smtp_host
from ..rules.defaults import channel_settings, section
from .admission import Admission, Costs, RateDeferred, RateRefused

# Provider "per day" limits are rolling 24 h windows and Graph's per-hour limits rolling 1 h ones (definitions).
DAY = timedelta(hours=24)
HOUR = timedelta(hours=1)
# (policy field, what it counts, window). "internal" is the recipients that are not external.
LIMIT_FIELDS = (
    ("daily_limit", "total", DAY),
    ("daily_external_limit", "external", DAY),
    ("daily_message_limit", "messages", DAY),
    ("hourly_external_limit", "external", HOUR),
    ("hourly_internal_limit", "internal", HOUR),
)
COLUMNS = ("total", "external", "messages")


@dataclass(frozen=True)
class Limit:
    name: str
    counts: str
    window: timedelta
    limit: int
    # What all mail may use (× budget headroom), and what campaigns may use (also × (1 − reserve)).
    usable: int
    bulk_usable: int
    source: str


@dataclass(frozen=True)
class Usage:
    day: dict
    hour: dict
    # The 24 h total is SES's SentLast24Hours plus what was sent since, not only this site's buckets.
    reported: bool = False

    def of(self, counts: str, window: timedelta) -> int:
        values = self.day if window == DAY else self.hour
        return values["total"] - values["external"] if counts == "internal" else values[counts]


def bucket_seconds() -> int:
    return int(section("usage")["bucket_seconds"])


def bucket_start(now: datetime) -> datetime:
    size = bucket_seconds()
    return datetime.fromtimestamp(math.floor(now.timestamp() / size) * size, tz=UTC)


def _candidates(name, policy, state, spec):
    yield getattr(policy, name), "operator"
    yield spec.get(name), "documented"
    if name == "daily_limit" and state.discovered_at is not None:
        yield state.discovered_daily, "reported"
    host = spec.get("host_profiles", {}).get(smtp_host(state.identity or ""))
    if host:
        yield host.get(name), "host"


def _reserve(policy) -> Decimal:
    if policy.transactional_reserve is not None:
        return Decimal(policy.transactional_reserve)
    return Decimal(str(section("lanes")["transactional_reserve"]))


def limits(policy, state) -> list[Limit]:
    """The budgets that apply to ``state``'s identity (none for the inbox channels)."""
    spec = channel_settings(policy.channel)
    headroom, reserve = Decimal(policy.budget_headroom), _reserve(policy)
    found = []
    for name, counts, window in LIMIT_FIELDS:
        if name not in spec:
            continue
        present = [(int(value), source) for value, source in _candidates(name, policy, state, spec) if value]
        if not present:
            continue
        value, source = min(present, key=lambda item: item[0])
        # Until the tenant's outbound spam policy is confirmed, campaigns also stay under the Standard preset.
        unconfirmed = name == "daily_limit" and "limits_confirmed" in spec and not policy.limits_confirmed
        bulk_value = min(value, spec["unconfirmed_bulk_daily_limit"]) if unconfirmed else value
        bulk_usable = math.floor(bulk_value * headroom * (1 - reserve))
        found.append(Limit(name, counts, window, value, math.floor(value * headroom), bulk_usable, source))
    return found


def _cost(costs: Costs, counts: str) -> int:
    return {"total": costs.budget, "external": costs.external, "messages": costs.messages}.get(counts, costs.internal)


def usage(state, now: datetime) -> Usage:
    """What ``state``'s identity used in the rolling day and hour, folding in what SES reported it sent."""
    size = timedelta(seconds=bucket_seconds())
    in_hour = Q(bucket_start__gt=now - HOUR - size)
    sums = {f"day_{column}": Sum(column, default=0) for column in COLUMNS}
    sums |= {f"hour_{column}": Sum(column, default=0, filter=in_hour) for column in COLUMNS}
    report_fresh = state.discovered_used_24h is not None and state.discovered_at and now - state.discovered_at < DAY
    if report_fresh:
        sums["since_report"] = Sum("total", default=0, filter=Q(bucket_start__gt=state.discovered_at - size))
    totals = DeliveryUsageBucket.objects.filter(state=state, bucket_start__gt=now - DAY - size).aggregate(**sums)
    day = {column: totals[f"day_{column}"] for column in COLUMNS}
    hour = {column: totals[f"hour_{column}"] for column in COLUMNS}
    reported = report_fresh and state.discovered_used_24h + totals["since_report"] > day["total"]
    if reported:
        day["total"] = state.discovered_used_24h + totals["since_report"]
    return Usage(day=day, hour=hour, reported=bool(reported))


def _ages_out(state, limit: Limit, excess: int, now: datetime) -> datetime | None:
    """When ``excess`` units of this site's usage in the window have aged out, or None when they never will."""
    size = timedelta(seconds=bucket_seconds())
    rows = DeliveryUsageBucket.objects.filter(state=state, bucket_start__gt=now - limit.window - size)
    aged = 0
    for start, total, external, messages in rows.order_by("bucket_start").values_list(
        "bucket_start", "total", "external", "messages"
    ):
        aged += {"total": total, "external": external, "messages": messages}.get(limit.counts, total - external)
        if aged >= excess:
            return start + size + limit.window
    return None


def check(state, policy, lane: str, costs: Costs, now: datetime) -> RateDeferred | None:
    """The deferral when ``costs`` do not fit a budget for ``lane`` now. Raises ``RateRefused`` for a request
    larger than the provider's whole limit, which no wait can admit."""
    found = limits(policy, state) if costs.counted else []
    used = usage(state, now) if found else None
    for limit in found:
        cost = _cost(costs, limit.counts)
        if cost == 0:
            continue
        if cost > limit.limit:
            raise RateRefused(f"budget:{limit.name}")
        allowed = limit.bulk_usable if lane == Lane.BULK else limit.usable
        excess = used.of(limit.counts, limit.window) + cost - allowed
        if excess <= 0:
            continue
        until = None
        if not (used.reported and limit.counts == "total" and limit.window == DAY):
            until = _ages_out(state, limit, excess, now)
        # What SES reported (or a headroom that leaves less than this request) ages out on no bucket of ours.
        recheck = channel_settings(policy.channel).get("quota_recheck_seconds") or limit.window.total_seconds()
        return RateDeferred(until or now + timedelta(seconds=recheck), f"budget:{limit.name}", now=now)
    return None


def add(state, costs: Costs, lane: str, now: datetime) -> datetime | None:
    """Count an admitted request; return the bucket it was counted in."""
    if not costs.counted:
        return None
    start = bucket_start(now)
    DeliveryUsageBucket.objects.get_or_create(state=state, bucket_start=start)
    DeliveryUsageBucket.objects.filter(state=state, bucket_start=start).update(
        total=F("total") + costs.budget,
        bulk=F("bulk") + (costs.budget if lane == Lane.BULK else 0),
        external=F("external") + costs.external,
        messages=F("messages") + costs.messages,
    )
    return start


def release(admission: Admission) -> None:
    """Give back what an admission counted (the provider did not take the request)."""
    costs = admission.costs
    if admission.bucket_start is None or not costs.counted:
        return
    bulk = costs.budget if admission.lane == Lane.BULK else 0
    DeliveryUsageBucket.objects.filter(state_id=admission.state_id, bucket_start=admission.bucket_start).update(
        total=Greatest(F("total") - costs.budget, 0),
        bulk=Greatest(F("bulk") - bulk, 0),
        external=Greatest(F("external") - costs.external, 0),
        messages=Greatest(F("messages") - costs.messages, 0),
    )


def purge(now: datetime) -> int:
    """Delete buckets older than ``usage.retention_seconds``; return how many."""
    cutoff = now - timedelta(seconds=section("usage")["retention_seconds"])
    deleted, _ = DeliveryUsageBucket.objects.filter(bucket_start__lt=cutoff).delete()
    return deleted
