import logging

from django.utils import timezone

from apps.authn.services.sms import publish_plain_sms
from apps.core.models import AWSCredentialConfig
from apps.mail.models import SmsRecipientLog
from apps.mail.services.personalize import personalize
from apps.mail.services.sms_audience import get_sms_recipients

logger = logging.getLogger(__name__)


def send_sms_campaign(campaign, sent_by):
    recipients = get_sms_recipients(campaign)
    _mark_campaign_sending(campaign, sent_by, len(recipients))

    config = AWSCredentialConfig.load()
    if not config.sns_configured:
        _fail_campaign_for_missing_sms_config(campaign)

    for recipient in recipients:
        _send_one_recipient(campaign, recipient)
        if (campaign.sent_count + campaign.failed_count) % 10 == 0:
            campaign.save(update_fields=["sent_count", "failed_count"])

    campaign.status = "sent" if campaign.failed_count < campaign.total_recipients else "failed"
    campaign.sent_at = timezone.now()
    campaign.save(update_fields=["status", "sent_count", "failed_count", "sent_at"])
    return {
        "total": campaign.total_recipients,
        "sent": campaign.sent_count,
        "failed": campaign.failed_count,
    }


def _send_one_recipient(campaign, recipient):
    try:
        context = _recipient_context(recipient)
        message = personalize(campaign.message, context)
        log = SmsRecipientLog.objects.create(
            campaign=campaign,
            member_id=recipient["member_id"],
            phone_number=recipient["phone"],
            recipient_name=recipient["full_name"],
            status="pending",
            provider="aws_sns",
        )
        message_id = publish_plain_sms(phone_number=recipient["phone"], message=message)
        _record_success(campaign, log, message_id)
    except Exception as exc:
        logger.exception("Failed to send SMS campaign %s to %s", campaign.pk, recipient.get("phone", ""))
        SmsRecipientLog.objects.update_or_create(
            campaign=campaign,
            phone_number=recipient["phone"],
            defaults={
                "member_id": recipient["member_id"],
                "recipient_name": recipient["full_name"],
                "status": "failed",
                "provider": "aws_sns",
                "error_message": str(exc),
            },
        )
        campaign.failed_count += 1


def _record_success(campaign, log, message_id: str):
    SmsRecipientLog.objects.filter(pk=log.pk, status="pending").update(
        status="sent",
        provider="aws_sns",
        error_message="",
        sns_message_id=message_id,
        sent_at=timezone.now(),
    )
    campaign.sent_count += 1


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
