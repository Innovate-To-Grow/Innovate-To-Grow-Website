"""Sending the recipients the delivery limits paused, for email and SMS campaigns alike.

Without the background worker a campaign is sent by an in-process runner, which pauses the remaining recipients
when the delivery limits hold mail back for long (a daily limit, a provider stop); the campaign ends partial.
"Resume paused recipients" sends exactly those: queued for the worker when background jobs are enabled, otherwise
by a new in-process runner.
"""

import logging
import uuid

from django.db import transaction
from django.utils import timezone

from apps.core.services.background_jobs import enqueue_job, jobs_enabled
from apps.core.services.helpers.in_process import start_in_process_task

from .channels import EMAIL, PAUSED_STATUS, SMS, DeliveryChannel, aggregate_campaign

logger = logging.getLogger("apps.mail.services.campaign.dispatch")
# A campaign whose recipients are still being sent is left alone: its runner or its jobs own them.
_BUSY_STATUSES = ("sending", "queued")


def resume_paused_email_recipients(campaign) -> int:
    """Send ``campaign``'s paused recipients again; return how many (0: none paused, or it is still sending)."""
    return _resume(EMAIL, campaign, _run_paused_email)


def resume_paused_sms_recipients(campaign) -> int:
    """The same for an SMS campaign; queued ones wait for SMS quiet hours to end, while the in-process sender
    refuses during them (``QuietHoursActive``)."""
    if not jobs_enabled():
        from apps.mail.services.sms.errors import QuietHoursActive
        from apps.mail.services.sms.quiet_hours import held_until

        until = held_until()
        if until is not None:
            raise QuietHoursActive(until)
    return _resume(SMS, campaign, _run_paused_sms)


def _resume(channel: DeliveryChannel, campaign, runner) -> int:
    if jobs_enabled():
        return _queue_paused(channel, campaign)
    return _start_paused_run(channel, campaign, runner)


def _queue_paused(channel: DeliveryChannel, campaign) -> int:
    now = timezone.now()
    available_at = channel.available_at(now)
    with transaction.atomic():
        campaign = channel.campaign_model.objects.select_for_update().get(pk=campaign.pk)
        if campaign.status in _BUSY_STATUSES:
            return 0
        logs = list(channel.log_model.objects.select_for_update().filter(campaign=campaign, status=PAUSED_STATUS))
        for log in logs:
            _reset(channel.log_model.objects.filter(pk=log.pk), now, available_at=available_at)
            enqueue_job(
                kind=channel.job_kind,
                # A fresh key: the log may already have a finished job from an earlier queued send.
                dedupe_key=f"{campaign.pk}:{log.pk}:resume:{uuid.uuid4().hex}",
                payload={"recipient_log_id": str(log.pk)},
                can_retry_after_claim=False,
                available_at=available_at,
            )
    if logs:
        aggregate_campaign(channel, campaign.pk)
    return len(logs)


def _start_paused_run(channel: DeliveryChannel, campaign, runner) -> int:
    now = timezone.now()
    with transaction.atomic():
        campaign = channel.campaign_model.objects.select_for_update().get(pk=campaign.pk)
        if campaign.status in _BUSY_STATUSES:
            return 0
        resumed = _reset(channel.log_model.objects.filter(campaign=campaign, status=PAUSED_STATUS), now)
        if not resumed:
            return 0
        channel.campaign_model.objects.filter(pk=campaign.pk).update(status="sending", error_message="", updated_at=now)
    prefix = "email" if channel is EMAIL else "sms"
    try:
        start_in_process_task(runner, campaign.pk, name=f"{prefix}-campaign-resume-{campaign.pk}", daemon=False)
    except Exception:
        aggregate_campaign(channel, campaign.pk)
        raise
    return resumed


def _reset(logs, now, *, available_at=None) -> int:
    return logs.update(
        status="pending",
        error_message="",
        attempts=0,
        available_at=available_at or now,
        claim_token=None,
        claimed_at=None,
        uncertain_at=None,
        updated_at=now,
    )


def _recipient(log, address_key: str, address: str) -> dict:
    """The audience row the campaign's send would have built for this log's recipient."""
    member = log.member
    return {
        "member_id": log.member_id,
        address_key: address,
        "first_name": getattr(member, "first_name", "") if member else "",
        "last_name": getattr(member, "last_name", "") if member else "",
        "full_name": log.recipient_name,
    }


def _pending_logs(channel: DeliveryChannel, campaign_id):
    logs = channel.log_model.objects.filter(campaign_id=campaign_id, status="pending").select_related("member")
    return [
        (_recipient(log, channel.recipient_address_key, getattr(log, channel.address_field)), log)
        for log in logs.order_by("created_at")
    ]


def _run_paused_email(campaign_id) -> None:
    from apps.mail.models import EmailCampaign
    from apps.mail.services.send_campaign.runner import send_to_recipients

    try:
        send_to_recipients(EmailCampaign.objects.get(pk=campaign_id), _pending_logs(EMAIL, campaign_id))
    except Exception:
        logger.exception("Resuming the paused recipients of email campaign %s failed", campaign_id)
        raise
    finally:
        aggregate_campaign(EMAIL, campaign_id)


def _run_paused_sms(campaign_id) -> None:
    from apps.mail.models import SmsCampaign
    from apps.mail.services.sms.sender import send_sms_to_recipients

    try:
        send_sms_to_recipients(SmsCampaign.objects.get(pk=campaign_id), _pending_logs(SMS, campaign_id))
    except Exception:
        logger.exception("Resuming the paused recipients of SMS campaign %s failed", campaign_id)
        raise
    finally:
        aggregate_campaign(SMS, campaign_id)
