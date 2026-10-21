"""The two delivery channels of a campaign (email, SMS) and the bookkeeping they share.

Each recipient of a queued campaign has a recipient log and one durable outbox job.
The channels differ only in their models, statuses and wording, described here once.
"""

from collections.abc import Callable
from dataclasses import dataclass

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from apps.core.models import BackgroundJob
from apps.mail.models import EmailCampaign, RecipientLog, SmsCampaign, SmsRecipientLog
from apps.mail.services.audience import get_recipients
from apps.mail.services.campaign.state import campaign_state
from apps.mail.services.sms.audience import get_sms_recipients

EMAIL_SUCCESS_STATUSES = frozenset({"sent", "delivered"})
EMAIL_PROVIDER_TERMINAL_STATUSES = frozenset({*EMAIL_SUCCESS_STATUSES, "bounced", "complained", "rejected"})
ACTIVE_STATUSES = ("pending", "processing", "retry")


@dataclass(frozen=True)
class DeliveryChannel:
    job_kind: str
    campaign_model: type
    log_model: type
    #: Recipient-log field holding the address, and the audience row key it comes from.
    address_field: str
    recipient_address_key: str
    #: Provider recorded on a freshly queued log.
    queued_provider: str
    not_draft_message: str
    success_statuses: frozenset
    #: Statuses counted as failed in the campaign totals.
    failed_statuses: tuple
    #: Statuses the outbox must never overwrite (provider-confirmed outcomes).
    terminal_statuses: frozenset
    recipients: Callable


EMAIL = DeliveryChannel(
    job_kind="mail.email_recipient",
    campaign_model=EmailCampaign,
    log_model=RecipientLog,
    address_field="email_address",
    recipient_address_key="email",
    queued_provider="",
    not_draft_message="Campaign is no longer in draft state.",
    success_statuses=EMAIL_SUCCESS_STATUSES,
    failed_statuses=("failed", "bounced", "complained", "rejected", "uncertain"),
    terminal_statuses=EMAIL_PROVIDER_TERMINAL_STATUSES,
    recipients=get_recipients,
)

SMS = DeliveryChannel(
    job_kind="mail.sms_recipient",
    campaign_model=SmsCampaign,
    log_model=SmsRecipientLog,
    address_field="phone_number",
    recipient_address_key="phone",
    queued_provider="aws_sns",
    not_draft_message="SMS campaign is no longer in draft state.",
    success_statuses=frozenset({"sent"}),
    failed_statuses=("failed", "uncertain"),
    terminal_statuses=frozenset({"sent"}),
    recipients=get_sms_recipients,
)

CHANNELS_BY_KIND = {channel.job_kind: channel for channel in (EMAIL, SMS)}


def aggregate_campaign(channel: DeliveryChannel, campaign_id) -> None:
    """Recount a campaign's totals and state from its recipient logs."""
    with transaction.atomic():
        campaign = channel.campaign_model.objects.select_for_update().filter(pk=campaign_id).first()
        if campaign is None:
            return
        statuses = {
            row["status"]: row["count"]
            for row in channel.log_model.objects.filter(campaign_id=campaign_id)
            .values("status")
            .annotate(count=Count("id"))
        }
        total = sum(statuses.values())
        sent = sum(statuses.get(status, 0) for status in sorted(channel.success_statuses))
        failed = sum(statuses.get(status, 0) for status in channel.failed_statuses)
        active = sum(statuses.get(status, 0) for status in ACTIVE_STATUSES)
        campaign.status = campaign_state(total=total, sent=sent, failed=failed, active=active)
        campaign.total_recipients = total
        campaign.sent_count = sent
        campaign.failed_count = failed
        if campaign.sent_at is None and not active:
            campaign.sent_at = timezone.now()
        campaign.error_message = "One or more deliveries need review." if failed else ""
        campaign.save(
            update_fields=[
                "status",
                "total_recipients",
                "sent_count",
                "failed_count",
                "sent_at",
                "error_message",
                "updated_at",
            ]
        )


def aggregate_email_campaign(campaign_id) -> None:
    aggregate_campaign(EMAIL, campaign_id)


def aggregate_sms_campaign(campaign_id) -> None:
    aggregate_campaign(SMS, campaign_id)


def mark_log_processing(channel: DeliveryChannel, log, job) -> bool:
    """Claim the recipient log for this job, only while the job still owns its outbox claim."""
    with transaction.atomic():
        owns_claim = (
            BackgroundJob.objects.select_for_update()
            .filter(
                pk=job.pk,
                status=BackgroundJob.Status.PROCESSING,
                claim_token=job.claim_token,
            )
            .exists()
        )
        if not owns_claim:
            return False
        return bool(
            channel.log_model.objects.filter(
                pk=log.pk,
                status__in=["pending", "retry", "processing"],
            ).update(
                status="processing",
                attempts=job.attempts,
                available_at=job.available_at,
                claim_token=job.claim_token,
                claimed_at=job.claimed_at,
                error_message="",
                updated_at=timezone.now(),
            )
        )


def release_failed_log(channel: DeliveryChannel, log, job, *, status, error_message, uncertain_at) -> None:
    """Record a delivery failure on a log this job still holds, freeing its claim."""
    channel.log_model.objects.filter(
        pk=log.pk,
        status="processing",
        claim_token=job.claim_token,
    ).update(
        status=status,
        error_message=error_message,
        uncertain_at=uncertain_at,
        claim_token=None,
        claimed_at=None,
        updated_at=timezone.now(),
    )
