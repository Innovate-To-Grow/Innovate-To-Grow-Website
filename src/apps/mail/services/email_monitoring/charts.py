"""The dashboard's chart data: series over time (hourly or daily buckets in the site's time zone, every bucket
present even when empty) and the ranked breakdowns. All of it is aggregated in the database."""

from datetime import datetime, time, timedelta

from django.db.models import Count, Max, Q
from django.db.models.functions import TruncDay, TruncHour, TruncMinute
from django.utils import timezone

from apps.core.models import EmailBounce, EmailCategory, OutboundEmail, OutboundEmailAttempt
from apps.core.services.email.telemetry import kind_label

from .scope import Scope

Status = OutboundEmail.Status
Outcome = OutboundEmailAttempt.Outcome
Classification = EmailBounce.Classification
FAILED = (Outcome.TRANSIENT, Outcome.PERMANENT, Outcome.UNCERTAIN)
BOUNCE_SERIES = (
    Classification.HARD,
    Classification.SOFT,
    Classification.REJECTED,
    Classification.DELAYED,
    Classification.UNKNOWN,
)
TOP_REASONS = 10
SERIES_LABELS = {
    "emails": "Emails",
    "accepted": "Accepted",
    "failed": "Failed",
    "uncertain": "Outcome unknown",
    "bounced": "Confirmed bounces",
    **dict(Classification.choices),
}


def buckets(start: datetime, end: datetime, unit: str) -> list[datetime]:
    """Every bucket start from the one holding ``start`` up to ``end``, aware, in the current time zone."""
    if unit in ("minute", "hour"):
        current = start.replace(second=0, microsecond=0)
        if unit == "hour":
            current = current.replace(minute=0)
        step = timedelta(minutes=1) if unit == "minute" else timedelta(hours=1)
        found = []
        while current < end:
            found.append(timezone.localtime(current))
            current += step
        return found
    day, last = timezone.localdate(start), timezone.localdate(end - timedelta(microseconds=1))
    found = []
    while day <= last:
        found.append(timezone.make_aware(datetime.combine(day, time.min)))
        day += timedelta(days=1)
    return found


def trunc(unit: str, field: str):
    function = {"minute": TruncMinute, "hour": TruncHour}.get(unit, TruncDay)
    return function(field, tzinfo=timezone.get_current_timezone())


def display(key: datetime, unit: str) -> str:
    local = timezone.localtime(key)
    return local.strftime("%b %d") if unit == "day" else local.strftime("%b %d %H:%M")


def series(rows, keys: list[datetime], names: tuple[str, ...], unit: str = "day") -> dict:
    """``{"labels", "display", "series": {name: [count per bucket]}, "table"}`` from rows of ``{"bucket", name...}``;
    ``table`` is the same data by row, for the chart's data-table view."""
    index = {key: position for position, key in enumerate(keys)}
    values = {name: [0] * len(keys) for name in names}
    for row in rows:
        position = index.get(row["bucket"])
        if position is None:
            continue
        for name in names:
            values[name][position] += row.get(name) or 0
    labels = [display(key, unit) for key in keys]
    return {
        "names": [{"key": name, "label": SERIES_LABELS.get(name, name)} for name in names],
        "labels": [key.isoformat() for key in keys],
        "display": labels,
        "series": values,
        "table": [
            {"label": label, "values": [values[name][position] for name in names]}
            for position, label in enumerate(labels)
            if any(values[name][position] for name in names)
        ],
    }


def volume(scope: Scope, keys) -> dict:
    rows = (
        scope.emails()
        .annotate(bucket=trunc(scope.bucket, "created_at"))
        .values("bucket")
        .order_by()
        .annotate(emails=Count("pk"))
    )
    return series(rows, keys, ("emails",), scope.bucket)


def api_outcomes(scope: Scope, keys) -> dict:
    rows = (
        scope.attempts()
        .annotate(bucket=trunc(scope.bucket, "started_at"))
        .values("bucket")
        .order_by()
        .annotate(
            accepted=Count("pk", filter=Q(outcome=Outcome.ACCEPTED)),
            failed=Count("pk", filter=Q(outcome__in=[Outcome.TRANSIENT, Outcome.PERMANENT])),
            uncertain=Count("pk", filter=Q(outcome=Outcome.UNCERTAIN)),
        )
    )
    return series(rows, keys, ("accepted", "failed", "uncertain"), scope.bucket)


def bounce_trend(scope: Scope, keys) -> dict:
    rows = (
        scope.bounces()
        .annotate(bucket=trunc(scope.bucket, "received_at"))
        .values("bucket")
        .order_by()
        .annotate(**{name: Count("pk", filter=Q(classification=name)) for name in BOUNCE_SERIES})
    )
    return series(rows, keys, BOUNCE_SERIES, scope.bucket)


def with_shares(rows: list[dict]) -> list[dict]:
    """Each row's ``count`` as a percentage of the largest, for a ranked bar list."""
    largest = max((row["count"] for row in rows), default=0)
    return [{**row, "share": round(100 * row["count"] / largest, 1) if largest else 0} for row in rows]


def http_errors(scope: Scope) -> list[dict]:
    """Failed attempts by HTTP status, or by what went wrong when Microsoft never answered."""
    totals: dict[str, int] = {}
    rows = (
        scope.attempts()
        .filter(outcome__in=FAILED)
        .values("http_status", "error_kind")
        .order_by()
        .annotate(count=Count("pk"))
    )
    for row in rows:
        label = f"HTTP {row['http_status']}" if row["http_status"] else kind_label(row["error_kind"]) or "Unknown"
        totals[label] = totals.get(label, 0) + row["count"]
    ranked = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    return with_shares([{"label": label, "count": count} for label, count in ranked])


def categories(scope: Scope) -> list[dict]:
    labels = dict(EmailCategory.choices)
    rows = scope.emails().values("category").annotate(count=Count("pk")).order_by("-count", "category")
    return with_shares(
        [{"key": row["category"], "label": labels.get(row["category"], row["category"]), **row} for row in rows]
    )


def failure_reasons(scope: Scope) -> list[dict]:
    """The commonest reasons sends failed: attempt errors, and emails the site stopped before any attempt."""
    attempt_rows = (
        scope.attempts()
        .filter(outcome__in=FAILED)
        .values("error_kind", "error_code", "error_message")
        .order_by()
        .annotate(count=Count("pk"), last_seen=Max("started_at"))
    )
    unsent_rows = (
        scope.emails()
        .filter(status=Status.NOT_SENT, attempt_count=0)
        .values("last_error_kind", "last_error")
        .order_by()
        .annotate(count=Count("pk"), last_seen=Max("updated_at"))
    )
    reasons = [
        {"kind": kind_label(row["error_kind"]), "code": row["error_code"], "message": row["error_message"], **row}
        for row in attempt_rows
    ] + [
        {"kind": kind_label(row["last_error_kind"]), "code": "", "message": row["last_error"], **row}
        for row in unsent_rows
    ]
    reasons.sort(key=lambda row: (-row["count"], row["kind"]))
    return reasons[:TOP_REASONS]


def bounce_reasons(scope: Scope) -> list[dict]:
    """The most frequent (category, status code, reason) of the failed recipients (delays left out)."""
    labels = dict(EmailBounce.Category.choices)
    rows = (
        scope.bounces()
        .exclude(classification=Classification.DELAYED)
        .values("category", "classification", "status_code", "reason")
        .annotate(count=Count("pk"), last_seen=Max("received_at"))
        .order_by("-count", "status_code")[:TOP_REASONS]
    )
    return [{"label": labels.get(row["category"], "Not classified yet"), **row} for row in rows]


def charts(scope: Scope) -> dict:
    keys = buckets(scope.start, scope.end, scope.bucket)
    return {
        "bucket": scope.bucket,
        "volume": volume(scope, keys),
        "api": api_outcomes(scope, keys),
        "bounces": bounce_trend(scope, keys),
        "http_errors": http_errors(scope),
        "categories": categories(scope),
    }
