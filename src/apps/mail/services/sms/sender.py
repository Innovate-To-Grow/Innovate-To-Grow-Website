"""The in-process SMS campaign sender, used while background jobs are off: one thread sends every recipient in turn.

It runs in the dedicated wait mode on the bulk lane, so each SMS waits for its slot (up to ``waits.dedicated_seconds``).
A recipient AWS throttles is sent again once the cooldown ends, never failed for it. When the delivery limits hold
SMS back for longer (the spend limit, an account stop), the rest of the recipients are paused and the campaign ends
partial; "Resume paused recipients" sends them later.
"""

import logging

from django.utils import timezone

from apps.authn.services.sms import PhoneVerificationBusy, publish_plain_sms
from apps.core.models import AWSCredentialConfig
from apps.core.services.background_jobs.delivery import deferral_of
from apps.core.services.delivery_rates import Lane, WaitMode, wait_mode
from apps.core.services.delivery_rates.rules.defaults import section
from apps.mail.models import SmsRecipientLog
from apps.mail.services.campaign.errors import unexpected_delivery_error_message
from apps.mail.services.campaign.personalize import personalize
from apps.mail.services.sms.audience import get_sms_recipients

logger = logging.getLogger(__name__)

PAUSED_LOG_MESSAGE = "Paused by delivery limits; send it with “Resume paused recipients”."


def send_sms_campaign(campaign, sent_by):
    recipients = get_sms_recipients(campaign)
    _mark_campaign_sending(campaign, sent_by, len(recipients))
    if not recipients:
        return _finalize_campaign(campaign)

    config = AWSCredentialConfig.load()
    if not config.sns_configured:
        _fail_campaign_for_missing_sms_config(campaign)

    logs = SmsRecipientLog.objects.bulk_create(
        [
            SmsRecipientLog(
                campaign=campaign,
                member_id=recipient["member_id"],
                phone_number=recipient["phone"],
                recipient_name=recipient["full_name"],
                status="pending",
                provider="aws_sns",
            )
            for recipient in recipients
        ]
    )
    send_sms_to_recipients(campaign, list(zip(recipients, logs, strict=True)))
    return _finalize_campaign(campaign)


def send_sms_to_recipients(campaign, pending) -> None:
    """Send each ``(recipient, log)`` on the bulk lane in turn; pause the rest when the delivery limits hold them
    back. Progress is saved every ``jobs.runner_refresh_recipients`` recipients."""
    refresh_every = section("jobs")["runner_refresh_recipients"]
    # Every admission in this thread may wait up to the dedicated cap for its slot instead of being deferred.
    with wait_mode(WaitMode.DEDICATED):
        for index, (recipient, log) in enumerate(pending, start=1):
            if not _send_one_recipient(campaign, recipient, log):
                pause_sms_recipients([held for _recipient, held in pending[index - 1 :]])
                break
            if index % refresh_every == 0:
                _refresh_campaign_progress(campaign)


def pause_sms_recipients(logs) -> int:
    """Mark recipients the delivery limits held back as paused (only those not yet sent or failed)."""
    return SmsRecipientLog.objects.filter(pk__in=[log.pk for log in logs], status="pending").update(
        status="paused", error_message=PAUSED_LOG_MESSAGE, updated_at=timezone.now()
    )


def _finalize_campaign(campaign):
    _refresh_campaign_progress(campaign)
    return {
        "total": campaign.total_recipients,
        "sent": campaign.sent_count,
        "failed": campaign.failed_count,
    }


def _refresh_campaign_progress(campaign):
    from apps.mail.services.campaign.dispatch import aggregate_sms_campaign

    # Derive progress from the persisted logs (sent, failed, paused, still pending) instead of counting in memory.
    aggregate_sms_campaign(campaign.pk)
    campaign.refresh_from_db(
        fields=["status", "total_recipients", "sent_count", "failed_count", "sent_at", "error_message"]
    )


def _send_one_recipient(campaign, recipient, log) -> bool:
    """Send to one recipient and record the outcome; False when the delivery limits held it back (left pending)."""
    try:
        message = personalize(campaign.message, _recipient_context(recipient))
        message_id = _send_when_taken(recipient["phone"], message)
        if message_id is None:
            return False
        _record_success(log, message_id)
    except Exception as exc:
        logger.exception("Failed to send SMS campaign %s to %s", campaign.pk, recipient.get("phone", ""))
        SmsRecipientLog.objects.filter(pk=log.pk, status="pending").update(
            status="failed",
            provider="aws_sns",
            error_message=unexpected_delivery_error_message(exc),
            updated_at=timezone.now(),
        )
    return True


def _send_when_taken(phone_number: str, message: str) -> str | None:
    """Send one SMS; None when the delivery limits hold it back for longer than this thread may wait.

    AWS throttling it sent nothing, so it is sent again: the next admission waits out the cooldown the throttle set.
    Throttles in a row open the channel's breaker after ``controller.persistent_throttle_count``, so this stops
    trying after as many and leaves the recipient for "Resume paused recipients".
    """
    for _attempt in range(section("controller")["persistent_throttle_count"]):
        try:
            return publish_plain_sms(phone_number=phone_number, message=message, lane=Lane.BULK)
        except PhoneVerificationBusy as exc:
            if deferral_of(exc) is not None:
                return None
            logger.info("AWS held back an SMS campaign message; sending it again after the cooldown.")
    return None


def _record_success(log, message_id: str):
    SmsRecipientLog.objects.filter(pk=log.pk, status="pending").update(
        status="sent",
        provider="aws_sns",
        error_message="",
        sns_message_id=message_id,
        sent_at=timezone.now(),
        updated_at=timezone.now(),
    )


def _recipient_context(recipient):
    return {
        "first_name": recipient["first_name"],
        "last_name": recipient["last_name"],
        "full_name": recipient["full_name"],
    }


def _mark_campaign_sending(campaign, sent_by, recipient_count):
    campaign.status = "sending"
    campaign.sent_by = sent_by
    campaign.total_recipients = recipient_count
    campaign.sent_count = 0
    campaign.failed_count = 0
    campaign.error_message = ""
    campaign.save(
        update_fields=[
            "status",
            "sent_by",
            "total_recipients",
            "sent_count",
            "failed_count",
            "error_message",
        ]
    )


def _fail_campaign_for_missing_sms_config(campaign):
    campaign.status = "failed"
    campaign.error_message = "SMS delivery is not configured. Check AWS Credentials in admin."
    campaign.save(update_fields=["status", "error_message"])
    raise RuntimeError("SMS delivery is not configured. Cannot send campaign.")
