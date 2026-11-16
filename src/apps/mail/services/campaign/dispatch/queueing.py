"""Queueing a campaign for the durable outbox: one recipient log and one outbox job per recipient, email or SMS."""

from django.db import transaction
from django.utils import timezone

from apps.core.services.background_jobs import enqueue_job
from apps.mail.models import EmailCampaign, SmsCampaign

from .channels import EMAIL, SMS, DeliveryChannel


def _queue_campaign(channel: DeliveryChannel, campaign, *, sent_by) -> dict[str, int]:
    """Create (or reset) one recipient log and one outbox job per recipient, atomically.

    Every job is due at once (an SMS queued inside quiet hours: when they end): the delivery-rate limiter paces them
    as they run, and the worker leaves the campaign lane unclaimed while it waits for its next slot, so jobs queued
    meanwhile still run first.
    """
    recipients = channel.recipients(campaign)
    now = timezone.now()
    available_at = channel.available_at(now)
    with transaction.atomic():
        campaign = channel.campaign_model.objects.select_for_update().get(pk=campaign.pk)
        if campaign.status != "draft":
            raise ValueError(channel.not_draft_message)
        for recipient in recipients:
            _queue_recipient(channel, campaign, recipient, available_at=available_at)
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


def _queue_recipient(channel: DeliveryChannel, campaign, recipient, *, available_at) -> None:
    """Create (or reset) one recipient log and its outbox job, both due at ``available_at``."""
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
            "available_at": available_at,
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
        available_at=available_at,
    )


def queue_email_campaign(campaign: EmailCampaign, *, sent_by) -> dict[str, int]:
    return _queue_campaign(EMAIL, campaign, sent_by=sent_by)


def queue_sms_campaign(campaign: SmsCampaign, *, sent_by) -> dict[str, int]:
    return _queue_campaign(SMS, campaign, sent_by=sent_by)
