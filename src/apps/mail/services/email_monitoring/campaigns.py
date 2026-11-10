"""Broadcast campaigns in the email telemetry: the comparison table of the overview, and one campaign's monitoring.

A campaign sends one message per recipient, so its message and recipient counts are the same. Recipients processed
before monitoring began have no telemetry: the page compares the telemetry with the campaign's own recipient log,
says how much of the campaign it covers, and shows the recipient log's counts as recorded at the time (nothing is
reconstructed into telemetry).
"""

from datetime import timedelta

from django.db.models import Count, F, Max, Min, Q, Sum
from django.db.models.functions import Coalesce

from apps.core.models import EmailBounce, OutboundEmail, OutboundEmailAttempt
from apps.core.services.email.telemetry import kind_label
from apps.mail.models import EmailCampaign, RecipientLog

from .charts import buckets, series, trunc
from .overview import FAILED_OUTCOMES, attempt_figures, message_figures, rate
from .scope import HOURLY_MAX_SPAN, Scope, monitoring_began

Status = OutboundEmail.Status
DeliveryStatus = OutboundEmail.DeliveryStatus
Outcome = OutboundEmailAttempt.Outcome
# A campaign's timeline uses minute buckets up to this span (most sends take minutes), then hours, then days.
MINUTE_MAX_SPAN = timedelta(hours=3)
COMPARISON_LIMIT = 20
FAILED_RECIPIENT_LIMIT = 200
# Recipient-log statuses of recipients not processed yet (they cannot have telemetry of a finished send).
UNPROCESSED_LOG_STATUSES = ("pending", "processing", "retry", "paused")


def comparisons(scope: Scope) -> list[dict]:
    rows = (
        scope.emails()
        .exclude(campaign_id=None)
        .values("campaign_id")
        .order_by()
        .annotate(
            emails=Count("pk"),
            accepted=Count("pk", filter=Q(status=Status.ACCEPTED)),
            failed=Count("pk", filter=Q(status__in=[Status.FAILED, Status.NOT_SENT])),
            uncertain=Count("pk", filter=Q(status=Status.UNCERTAIN)),
            bounced=Count("pk", filter=Q(delivery_status=DeliveryStatus.FAILURE_CONFIRMED)),
            retries=Coalesce(Sum(F("attempt_count") - 1, filter=Q(attempt_count__gt=0)), 0),
            first_sent=Min("created_at"),
        )
        .order_by("-first_sent")[:COMPARISON_LIMIT]
    )
    rows = list(rows)
    names = dict(EmailCampaign.objects.filter(pk__in=[row["campaign_id"] for row in rows]).values_list("pk", "name"))
    for row in rows:
        row["name"] = names.get(row["campaign_id"]) or "(deleted campaign)"
        row["acceptance_rate"] = rate(row["accepted"], row["accepted"] + row["failed"] + row["uncertain"])
        row["bounce_rate"] = rate(row["bounced"], row["accepted"])
    return rows


def _timeline(emails, attempts, bounces) -> dict | None:
    span = attempts.aggregate(first=Min("started_at"), last=Max("started_at"))
    if span["first"] is None:
        return None
    end = max(span["last"], bounces.aggregate(last=Max("received_at"))["last"] or span["last"])
    length = end - span["first"]
    unit = "minute" if length <= MINUTE_MAX_SPAN else ("hour" if length <= HOURLY_MAX_SPAN else "day")
    keys = buckets(span["first"], end + timedelta(seconds=1), unit)
    attempt_rows = (
        attempts.annotate(bucket=trunc(unit, "started_at"))
        .values("bucket")
        .order_by()
        .annotate(
            accepted=Count("pk", filter=Q(outcome=Outcome.ACCEPTED)),
            failed=Count("pk", filter=Q(outcome__in=[Outcome.TRANSIENT, Outcome.PERMANENT])),
            uncertain=Count("pk", filter=Q(outcome=Outcome.UNCERTAIN)),
        )
    )
    bounce_rows = (
        bounces.annotate(bucket=trunc(unit, "received_at"))
        .values("bucket")
        .order_by()
        .annotate(bounced=Count("pk", filter=~Q(classification=EmailBounce.Classification.DELAYED)))
    )
    names = ("accepted", "failed", "uncertain", "bounced")
    timeline = series([*attempt_rows, *bounce_rows], keys, names, unit)
    timeline["bucket"] = unit
    return timeline


def failed_recipients(emails) -> tuple[list[OutboundEmail], int]:
    rows = emails.filter(
        Q(status__in=[Status.FAILED, Status.NOT_SENT, Status.UNCERTAIN])
        | Q(delivery_status__in=[DeliveryStatus.FAILURE_CONFIRMED, DeliveryStatus.DELAYED])
    ).order_by("-last_attempt_at", "recipient")
    return list(rows[:FAILED_RECIPIENT_LIMIT]), rows.count()


def campaign_monitoring(campaign: EmailCampaign) -> dict:
    emails = OutboundEmail.objects.filter(campaign_id=campaign.pk)
    attempts = OutboundEmailAttempt.objects.filter(email__campaign_id=campaign.pk)
    bounces = EmailBounce.objects.filter(campaign_id=campaign.pk)
    messages = message_figures(emails)
    errors = (
        attempts.filter(outcome__in=FAILED_OUTCOMES)
        .values("error_kind")
        .order_by()
        .annotate(count=Count("pk"))
        .order_by("-count")
    )
    by_class = dict(bounces.values_list("classification").order_by().annotate(count=Count("pk")))
    failed, failed_total = failed_recipients(emails)
    recipient_log = dict(
        RecipientLog.objects.filter(campaign=campaign).values_list("status").order_by().annotate(count=Count("pk"))
    )
    processed = sum(count for status, count in recipient_log.items() if status not in UNPROCESSED_LOG_STATUSES)
    return {
        "messages": messages,
        "attempts": attempt_figures(attempts),
        "error_kinds": [{"kind": row["error_kind"], "label": kind_label(row["error_kind"]), **row} for row in errors],
        "bounce_classes": [
            {"key": key, "label": label, "count": by_class.get(key, 0)}
            for key, label in EmailBounce.Classification.choices
        ],
        "failed": failed,
        "failed_total": failed_total,
        "timeline": _timeline(emails, attempts, bounces),
        "recipient_log": recipient_log,
        "processed_recipients": processed,
        "monitoring_began": monitoring_began(),
        # "none": processed before monitoring began; "partial": some recipients have no telemetry.
        "coverage": "none"
        if processed and not messages["total"]
        else ("partial" if messages["total"] < processed else "full"),
    }
