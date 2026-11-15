from django.db.models import Count, Max

from apps.core.models import EmailBounce, OutboundEmail, OutboundEmailAttempt
from apps.core.services.email.telemetry import kind_label

from ..scope import Scope

Status = OutboundEmail.Status


Outcome = OutboundEmailAttempt.Outcome


Classification = EmailBounce.Classification


FAILED = (Outcome.TRANSIENT, Outcome.PERMANENT, Outcome.UNCERTAIN)


TOP_REASONS = 10


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
