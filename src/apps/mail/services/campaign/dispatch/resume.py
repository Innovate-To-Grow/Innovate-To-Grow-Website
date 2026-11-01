"""Sending the recipients the delivery limits paused.

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
from apps.mail.models import EmailCampaign, RecipientLog

from .channels import EMAIL, PAUSED_STATUS, aggregate_email_campaign

logger = logging.getLogger("apps.mail.services.campaign.dispatch")
# A campaign whose recipients are still being sent is left alone: its runner or its jobs own them.
_BUSY_STATUSES = ("sending", "queued")


def resume_paused_email_recipients(campaign: EmailCampaign) -> int:
    """Send ``campaign``'s paused recipients again; return how many (0: none paused, or it is still sending)."""
    if jobs_enabled():
        return _queue_paused(campaign)
    return _start_paused_run(campaign)


def _queue_paused(campaign: EmailCampaign) -> int:
    now = timezone.now()
    with transaction.atomic():
        campaign = EmailCampaign.objects.select_for_update().get(pk=campaign.pk)
        if campaign.status in _BUSY_STATUSES:
            return 0
        logs = list(RecipientLog.objects.select_for_update().filter(campaign=campaign, status=PAUSED_STATUS))
        for log in logs:
            _reset(RecipientLog.objects.filter(pk=log.pk), now)
            enqueue_job(
                kind=EMAIL.job_kind,
                # A fresh key: the log may already have a finished job from an earlier queued send.
                dedupe_key=f"{campaign.pk}:{log.pk}:resume:{uuid.uuid4().hex}",
                payload={"recipient_log_id": str(log.pk)},
                can_retry_after_claim=False,
                available_at=now,
            )
    if logs:
        aggregate_email_campaign(campaign.pk)
    return len(logs)


def _start_paused_run(campaign: EmailCampaign) -> int:
    now = timezone.now()
    with transaction.atomic():
        campaign = EmailCampaign.objects.select_for_update().get(pk=campaign.pk)
        if campaign.status in _BUSY_STATUSES:
            return 0
        resumed = _reset(RecipientLog.objects.filter(campaign=campaign, status=PAUSED_STATUS), now)
        if not resumed:
            return 0
        EmailCampaign.objects.filter(pk=campaign.pk).update(status="sending", error_message="", updated_at=now)
    try:
        start_in_process_task(_run_paused, campaign.pk, name=f"email-campaign-resume-{campaign.pk}", daemon=False)
    except Exception:
        aggregate_email_campaign(campaign.pk)
        raise
    return resumed


def _reset(logs, now) -> int:
    return logs.update(
        status="pending",
        error_message="",
        attempts=0,
        available_at=now,
        claim_token=None,
        claimed_at=None,
        uncertain_at=None,
        updated_at=now,
    )


def _recipient(log) -> dict:
    """The audience row ``send_campaign`` would have built for this log's recipient."""
    member = log.member
    return {
        "member_id": log.member_id,
        "email": log.email_address,
        "first_name": getattr(member, "first_name", "") if member else "",
        "last_name": getattr(member, "last_name", "") if member else "",
        "full_name": log.recipient_name,
    }


def _run_paused(campaign_id) -> None:
    from apps.mail.services.send_campaign.runner import send_to_recipients

    try:
        campaign = EmailCampaign.objects.get(pk=campaign_id)
        logs = RecipientLog.objects.filter(campaign=campaign, status="pending").select_related("member")
        send_to_recipients(campaign, [(_recipient(log), log) for log in logs.order_by("created_at")])
    except Exception:
        logger.exception("Resuming the paused recipients of email campaign %s failed", campaign_id)
        raise
    finally:
        aggregate_email_campaign(campaign_id)
