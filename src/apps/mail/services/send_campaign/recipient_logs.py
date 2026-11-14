"""A campaign recipient's log row as it is sent: paused, skipped as suppressed, or recording the provider's answer."""

from django.utils import timezone

from apps.mail.models import RecipientLog
from apps.mail.services.suppression import SKIPPED_MESSAGE

PAUSED_LOG_MESSAGE = "Paused by delivery limits; send it with “Resume paused recipients”."


def pause_recipients(logs) -> int:
    """Mark recipients the delivery limits held back as paused (only those not yet sent or failed)."""
    return RecipientLog.objects.filter(pk__in=[log.pk for log in logs], status="pending").update(
        status="paused", error_message=PAUSED_LOG_MESSAGE, updated_at=timezone.now()
    )


def skip_suppressed_log(log, *, claim_token=None) -> bool:
    """Record that ``log``'s address is suppressed and was not sent, only while it is still unsent (and, for a queued
    job, still claimed by that job: ``claim_token``); True when this call recorded it."""
    logs = RecipientLog.objects.filter(pk=log.pk)
    if claim_token is not None:
        logs = logs.filter(status="processing", claim_token=claim_token)
    else:
        logs = logs.filter(status__in=("pending", "retry", "paused"))
    return bool(
        logs.update(
            status="failed",
            provider="",
            error_message=SKIPPED_MESSAGE,
            claim_token=None,
            claimed_at=None,
            uncertain_at=None,
            updated_at=timezone.now(),
        )
    )


def _configured_provider(config):
    if config is None:
        return ""
    return getattr(config, "provider", "")


def _record_send_result(campaign, log, result):
    updated = RecipientLog.objects.filter(pk=log.pk, status="pending").update(
        status="failed" if result.error else "sent",
        provider=result.provider,
        error_message=result.error,
        sent_at=None if result.error else timezone.now(),
        provider_message_id=result.message_id,
    )
    if updated == 0:
        log.refresh_from_db()
        if log.status in {"bounced", "complained", "rejected", "failed"}:
            campaign.failed_count += 1
        else:
            campaign.sent_count += 1
    elif result.error:
        campaign.failed_count += 1
    else:
        campaign.sent_count += 1
