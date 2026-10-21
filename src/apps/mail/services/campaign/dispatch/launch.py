"""Starting a campaign send: queued per recipient for the worker, or the legacy in-process run."""

import logging

from django.db import transaction
from django.utils import timezone

from apps.core.services.background_jobs import enqueue_job, jobs_enabled
from apps.core.services.helpers.in_process import start_in_process_task
from apps.mail.models import EmailCampaign, SmsCampaign

from .channels import EMAIL, SMS, DeliveryChannel

logger = logging.getLogger("apps.mail.services.campaign.dispatch")


def dispatch_email_campaign(campaign: EmailCampaign, *, sent_by):
    if not jobs_enabled():
        return _start_in_process_email_campaign(campaign, sent_by=sent_by)
    return queue_email_campaign(campaign, sent_by=sent_by)


def dispatch_sms_campaign(campaign: SmsCampaign, *, sent_by):
    if not jobs_enabled():
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

    from apps.mail.services.send_campaign import send_campaign

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

    from apps.mail.services.sms.sender import send_sms_campaign

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


def _queue_campaign(channel: DeliveryChannel, campaign, *, sent_by) -> dict[str, int]:
    """Create (or reset) one recipient log and one outbox job per recipient, atomically."""
    recipients = channel.recipients(campaign)
    now = timezone.now()
    with transaction.atomic():
        campaign = channel.campaign_model.objects.select_for_update().get(pk=campaign.pk)
        if campaign.status != "draft":
            raise ValueError(channel.not_draft_message)
        for recipient in recipients:
            log, _created = channel.log_model.objects.update_or_create(
                campaign=campaign,
                **{channel.address_field: recipient[channel.recipient_address_key]},
                defaults={
                    "member_id": recipient["member_id"],
                    "recipient_name": recipient["full_name"],
                    "status": "pending",
                    "provider": channel.queued_provider,
                    "error_message": "",
                    "attempts": 0,
                    "available_at": now,
                    "claim_token": None,
                    "claimed_at": None,
                    "uncertain_at": None,
                },
            )
            enqueue_job(
                kind=channel.job_kind,
                dedupe_key=f"{campaign.pk}:{log.pk}",
                payload={"recipient_log_id": str(log.pk)},
                can_retry_after_claim=False,
            )
        campaign.status = "queued" if recipients else "sent"
        campaign.sent_by = sent_by
        campaign.total_recipients = len(recipients)
        campaign.sent_count = 0
        campaign.failed_count = 0
        campaign.error_message = ""
        campaign.sent_at = now if not recipients else None
        campaign.save(
            update_fields=[
                "status",
                "sent_by",
                "total_recipients",
                "sent_count",
                "failed_count",
                "error_message",
                "sent_at",
                "updated_at",
            ]
        )
    return {"total": len(recipients), "sent": 0, "failed": 0}


def queue_email_campaign(campaign: EmailCampaign, *, sent_by) -> dict[str, int]:
    return _queue_campaign(EMAIL, campaign, sent_by=sent_by)


def queue_sms_campaign(campaign: SmsCampaign, *, sent_by) -> dict[str, int]:
    return _queue_campaign(SMS, campaign, sent_by=sent_by)
