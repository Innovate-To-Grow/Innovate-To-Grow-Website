"""One outgoing email's full operational history: every attempt with its error details, and the bounce reports
matched to it, with what each status does and does not prove."""

from datetime import timedelta

from django.conf import settings
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.core.models import EmailCategory, OutboundEmail, OutboundEmailAttempt
from apps.core.services.email.telemetry import kind_label
from apps.mail.models import EmailCampaign

Status = OutboundEmail.Status
DeliveryStatus = OutboundEmail.DeliveryStatus

STATUS_MEANING = {
    Status.PENDING: "No final answer yet: an attempt is in progress, or the delivery rate is holding the email back.",
    Status.ACCEPTED: (
        "The provider accepted the email for delivery (Microsoft Graph: HTTP 202). This only means it was queued: "
        "it does not prove the email reached the recipient's mailbox."
    ),
    Status.FAILED: "The provider refused the email, or could not be reached; nothing was queued for delivery.",
    Status.UNCERTAIN: (
        "The outcome is unknown (the response was lost, or the provider answered ambiguously): the email may have "
        "been sent, so it is never retried automatically."
    ),
    Status.NOT_SENT: "The site stopped the email before submitting it (configuration, delivery limits, composition).",
}
DELIVERY_MEANING = {
    DeliveryStatus.NOT_APPLICABLE: "The email was never accepted, so there is no delivery to report on.",
    DeliveryStatus.UNKNOWN: (
        "No bounce report has been matched to this email. That is not proof of delivery: a report can arrive "
        "later, or may not be matched reliably."
    ),
    DeliveryStatus.DELAYED: "A delivery-delay report was received; the receiving server was still retrying.",
    DeliveryStatus.FAILURE_CONFIRMED: "A bounce report confirms that delivery failed for at least one recipient.",
}


def _admin_link(name: str, *args) -> str:
    try:
        return reverse(name, args=args)
    except NoReverseMatch:
        return ""


def _source_link(email: OutboundEmail) -> str:
    if email.source_type == "mail.recipientlog" and email.source_id:
        return _admin_link("admin:mail_recipientlog_change", email.source_id)
    if email.source_type == "event.eventregistration" and email.source_id:
        return _admin_link("admin:event_eventregistration_change", email.source_id)
    return ""


def _attempt_row(attempt: OutboundEmailAttempt, stale_before) -> dict:
    interrupted = attempt.outcome == OutboundEmailAttempt.Outcome.IN_PROGRESS and attempt.started_at < stale_before
    return {
        "attempt": attempt,
        "kind": kind_label(attempt.error_kind),
        "interrupted": interrupted,
        "diagnostics": sorted((attempt.diagnostics or {}).items()),
    }


def email_detail(email: OutboundEmail) -> dict:
    stale_before = timezone.now() - timedelta(seconds=settings.EMAIL_MONITORING["attempt_stale_seconds"])
    campaign = EmailCampaign.objects.filter(pk=email.campaign_id).first() if email.campaign_id else None
    return {
        "email": email,
        "attempts": [_attempt_row(attempt, stale_before) for attempt in email.attempts.order_by("attempt_number")],
        "bounces": list(email.bounces.order_by("received_at")),
        "campaign": campaign,
        "campaign_link": _admin_link("admin:mail_emailcampaign_change", campaign.pk) if campaign else "",
        "source_link": _source_link(email),
        "job_link": _admin_link("admin:core_backgroundjob_change", email.job_id) if email.job_id else "",
        "status_meaning": STATUS_MEANING.get(email.status, ""),
        "delivery_meaning": DELIVERY_MEANING.get(email.delivery_status, ""),
        "kind": kind_label(email.last_error_kind),
        "is_probe": email.category == EmailCategory.ACCESS_CHECK,
    }
