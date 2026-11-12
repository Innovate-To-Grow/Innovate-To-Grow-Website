"""The dashboard's headline figures, kept apart by level so they are never mixed:

- message level: logical emails (one per message, however many attempts it took);
- recipient level: the envelope recipients of those messages, and the recipients a bounce report proves failed;
- attempt level: every provider call, retries included (429 throttles, response times).

"API accepted" means the provider queued the message (Microsoft Graph ``202 Accepted``), never that it was
delivered: only a bounce report proves anything about delivery, and then only a failure.
"""

from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import Coalesce

from apps.core.models import EmailBounce, OutboundEmail, OutboundEmailAttempt
from apps.core.services.email.telemetry import kind_label

from .scope import Scope

Status = OutboundEmail.Status
DeliveryStatus = OutboundEmail.DeliveryStatus
Outcome = OutboundEmailAttempt.Outcome
FAILED_OUTCOMES = (Outcome.TRANSIENT, Outcome.PERMANENT, Outcome.UNCERTAIN)


def rate(part, whole) -> float | None:
    """``part`` as a percentage of ``whole`` (one decimal), or None when there is no whole to compare with."""
    return round(100 * part / whole, 1) if whole else None


def message_figures(emails) -> dict:
    figures = emails.aggregate(
        total=Count("pk"),
        accepted=Count("pk", filter=Q(status=Status.ACCEPTED)),
        failed=Count("pk", filter=Q(status=Status.FAILED)),
        uncertain=Count("pk", filter=Q(status=Status.UNCERTAIN)),
        not_sent=Count("pk", filter=Q(status=Status.NOT_SENT)),
        pending=Count("pk", filter=Q(status=Status.PENDING)),
        bounced=Count("pk", filter=Q(delivery_status=DeliveryStatus.FAILURE_CONFIRMED)),
        delayed=Count("pk", filter=Q(delivery_status=DeliveryStatus.DELAYED)),
        retried=Count("pk", filter=Q(attempt_count__gt=1)),
        recipients=Coalesce(Sum("recipient_count"), 0),
        accepted_recipients=Coalesce(Sum("recipient_count", filter=Q(status=Status.ACCEPTED)), 0),
        failed_recipients=Coalesce(Sum("recipient_count", filter=Q(status__in=[Status.FAILED, Status.NOT_SENT])), 0),
    )
    submitted = figures["accepted"] + figures["failed"] + figures["uncertain"]
    figures["submitted"] = submitted
    figures["api_success_rate"] = rate(figures["accepted"], submitted)
    figures["bounce_rate"] = rate(figures["bounced"], figures["accepted"])
    return figures


def attempt_figures(attempts) -> dict:
    figures = attempts.aggregate(
        total=Count("pk"),
        accepted=Count("pk", filter=Q(outcome=Outcome.ACCEPTED)),
        failed=Count("pk", filter=Q(outcome__in=[Outcome.TRANSIENT, Outcome.PERMANENT])),
        uncertain=Count("pk", filter=Q(outcome=Outcome.UNCERTAIN)),
        not_sent=Count("pk", filter=Q(outcome=Outcome.NOT_SENT)),
        retries=Count("pk", filter=Q(attempt_number__gt=1)),
        throttled=Count("pk", filter=Q(http_status=429)),
        avg_response_ms=Avg("response_ms", filter=Q(response_ms__isnull=False, http_status__isnull=False)),
    )
    answered = figures["accepted"] + figures["failed"] + figures["uncertain"]
    figures["success_rate"] = rate(figures["accepted"], answered)
    figures["avg_response_ms"] = round(figures["avg_response_ms"]) if figures["avg_response_ms"] is not None else None
    return figures


def bounce_figures(bounces, emails) -> dict:
    """Reports received in the range, and the recipients they prove failed for emails sent in it."""
    reports = bounces.aggregate(
        total=Count("pk"),
        unmatched=Count("pk", filter=Q(email__isnull=True)),
        inferred=Count("pk", filter=Q(match_method=EmailBounce.MatchMethod.RECIPIENT)),
        delayed=Count("pk", filter=Q(classification=EmailBounce.Classification.DELAYED)),
    )
    confirmed = EmailBounce.objects.filter(email__in=emails.values("pk")).exclude(
        classification=EmailBounce.Classification.DELAYED
    )
    # The model's ordering (received_at) must not join the DISTINCT, or one recipient with two reports counts twice.
    reports["bounced_recipients"] = confirmed.order_by().values("email_id", "recipient").distinct().count()
    return reports


def latest_error(attempts) -> dict | None:
    attempt = (
        attempts.filter(outcome__in=FAILED_OUTCOMES)
        .select_related("email")
        .order_by("-started_at")
        .only(
            "started_at",
            "http_status",
            "error_kind",
            "error_code",
            "inner_error_code",
            "error_message",
            "request_id",
            "email__id",
            "email__recipient",
            "email__category",
        )
        .first()
    )
    if attempt is None:
        return None
    return {
        "at": attempt.started_at,
        "email_id": attempt.email_id,
        "recipient": attempt.email.recipient,
        "category": attempt.email.get_category_display(),
        "http_status": attempt.http_status,
        "kind": kind_label(attempt.error_kind),
        "code": attempt.inner_error_code or attempt.error_code,
        "message": attempt.error_message,
        "request_id": attempt.request_id,
    }


def overview(scope: Scope) -> dict:
    emails = scope.emails()
    attempts = scope.attempts()
    messages = message_figures(emails)
    bounces = bounce_figures(scope.bounces(), emails)
    bounces["recipient_bounce_rate"] = rate(bounces["bounced_recipients"], messages["accepted_recipients"])
    return {
        "messages": messages,
        "attempts": attempt_figures(attempts),
        "bounces": bounces,
        "latest_error": latest_error(attempts),
    }
