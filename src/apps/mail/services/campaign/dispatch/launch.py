"""Starting a campaign send: queued per recipient for the worker, or the legacy in-process run."""

import logging

from django.utils import timezone

from apps.core.services.background_jobs import jobs_enabled
from apps.core.services.helpers.in_process import start_in_process_task
from apps.mail.models import EmailCampaign, SmsCampaign
from apps.mail.services.campaign.dispatch.queueing import queue_email_campaign, queue_sms_campaign

logger = logging.getLogger("apps.mail.services.campaign.dispatch")


def dispatch_email_campaign(campaign: EmailCampaign, *, sent_by):
    if not jobs_enabled():
        return _start_in_process_email_campaign(campaign, sent_by=sent_by)
    return queue_email_campaign(campaign, sent_by=sent_by)


def dispatch_sms_campaign(campaign: SmsCampaign, *, sent_by):
    """Queue the campaign (inside SMS quiet hours its texts wait for them to end), or start the in-process sender,
    which cannot wait: during quiet hours it refuses with ``QuietHoursActive``. A message whose links are turned
    off raises ``LinksDisabled``; both before anything changes."""
    from apps.mail.services.sms.content.compose import refuse_unsendable
    from apps.mail.services.sms.policy.errors import QuietHoursActive
    from apps.mail.services.sms.policy.quiet_hours import held_until

    refuse_unsendable(campaign)
    if not jobs_enabled():
        until = held_until()
        if until is not None:
            raise QuietHoursActive(until)
        return _start_in_process_sms_campaign(campaign, sent_by=sent_by)
    return queue_sms_campaign(campaign, sent_by=sent_by)


def _start_in_process_email_campaign(campaign: EmailCampaign, *, sent_by) -> dict[str, int]:
    """Preserve the legacy non-blocking send path until a worker is deployed."""

    updated = EmailCampaign.objects.filter(pk=campaign.pk, status="draft").update(
        status="sending",
        sent_by_id=sent_by.pk,
        sent_count=0,
        failed_count=0,
        error_message="",
        sent_at=None,
        updated_at=timezone.now(),
    )
    if not updated:
        raise ValueError("Campaign is no longer in draft state.")
    try:
        start_in_process_task(
            _run_in_process_email_campaign,
            campaign.pk,
            sent_by.pk,
            name=f"email-campaign-{campaign.pk}",
            daemon=False,
        )
    except Exception:
        EmailCampaign.objects.filter(pk=campaign.pk, status="sending").update(
            status="failed",
            error_message="Campaign send could not be started. Check server logs for details.",
            updated_at=timezone.now(),
        )
        raise
    return {"total": 0, "sent": 0, "failed": 0}


def _run_in_process_email_campaign(campaign_id, sent_by_id) -> None:
    from django.contrib.auth import get_user_model

    from apps.mail.services.campaign.send import send_campaign

    try:
        campaign = EmailCampaign.objects.get(pk=campaign_id)
        sent_by = get_user_model().objects.get(pk=sent_by_id)
        send_campaign(campaign, sent_by=sent_by)
    except Exception:
        logger.exception("Background send failed for email campaign %s", campaign_id)
        EmailCampaign.objects.filter(pk=campaign_id, status__in=["draft", "sending"]).update(
            status="failed",
            error_message="Campaign send failed. Check server logs for details.",
            updated_at=timezone.now(),
        )
        raise


def _start_in_process_sms_campaign(campaign: SmsCampaign, *, sent_by) -> dict[str, int]:
    updated = SmsCampaign.objects.filter(pk=campaign.pk, status="draft").update(
        status="sending",
        sent_by_id=sent_by.pk,
        sent_count=0,
        failed_count=0,
        error_message="",
        sent_at=None,
        updated_at=timezone.now(),
    )
    if not updated:
        raise ValueError("SMS campaign is no longer in draft state.")
    try:
        start_in_process_task(
            _run_in_process_sms_campaign,
            campaign.pk,
            sent_by.pk,
            name=f"sms-campaign-{campaign.pk}",
            daemon=False,
        )
    except Exception:
        SmsCampaign.objects.filter(pk=campaign.pk, status="sending").update(
            status="failed",
            error_message="SMS campaign send could not be started. Check server logs for details.",
            updated_at=timezone.now(),
        )
        raise
    return {"total": 0, "sent": 0, "failed": 0}


def _run_in_process_sms_campaign(campaign_id, sent_by_id) -> None:
    from django.contrib.auth import get_user_model

    from apps.mail.services.sms.delivery.sender import send_sms_campaign

    try:
        campaign = SmsCampaign.objects.get(pk=campaign_id)
        sent_by = get_user_model().objects.get(pk=sent_by_id)
        send_sms_campaign(campaign, sent_by=sent_by)
    except Exception:
        logger.exception("Background send failed for SMS campaign %s", campaign_id)
        SmsCampaign.objects.filter(pk=campaign_id, status__in=["draft", "sending"]).update(
            status="failed",
            error_message="SMS campaign send failed. Check server logs for details.",
            updated_at=timezone.now(),
        )
        raise
