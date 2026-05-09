import logging
import time

from django.conf import settings
from django.utils import timezone

from core.models import EmailServiceConfig
from mail.models import MagicLoginToken, RecipientLog

from ..audience import get_recipients
from ..personalize import personalize
from ..preview import render_email_html
from ..unsubscribe_token import build_oneclick_unsubscribe_url
from .transport import _get_configuration_set_name, _get_ses_client, _send_via_ses

logger = logging.getLogger(__name__)


def send_campaign(campaign, sent_by):
    config = EmailServiceConfig.load()
    recipients = get_recipients(campaign)
    _mark_campaign_sending(campaign, sent_by, len(recipients))

    ses_client = _get_ses_client(config)
    if ses_client is None:
        _fail_campaign_for_missing_ses(campaign)

    send_timing = SendTiming(config.ses_max_send_rate or 0)
    configuration_set = _get_configuration_set_name(config)
    if not configuration_set:
        logger.warning(
            "No SES configuration set configured; bounce/complaint tracking disabled for campaign %s",
            campaign.pk,
        )

    for recipient in recipients:
        send_timing.wait_if_needed()
        _send_one_recipient(campaign, config, ses_client, configuration_set, recipient)
        send_timing.mark_sent()
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


class SendTiming:
    def __init__(self, send_rate: float):
        self.min_interval = (1.0 / send_rate) if send_rate > 0 else 0
        self.last_send_time = 0.0

    def wait_if_needed(self):
        if self.min_interval <= 0 or self.last_send_time <= 0:
            return
        elapsed = time.monotonic() - self.last_send_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)

    def mark_sent(self):
        self.last_send_time = time.monotonic()


def _send_one_recipient(campaign, config, ses_client, configuration_set, recipient):
    try:
        context = _recipient_context(recipient, campaign)
        subject = personalize(campaign.subject, context)
        body_html = personalize(campaign.body, context)
        unsubscribe_url = _unsubscribe_url_for(campaign, recipient)
        wrapped_html = render_email_html(body_html, unsubscribe_url=unsubscribe_url)
        log = RecipientLog.objects.create(
            campaign=campaign,
            member_id=recipient["member_id"],
            email_address=recipient["email"],
            recipient_name=recipient["full_name"],
            status="pending",
        )
        result = _send_via_ses(
            ses_client=ses_client,
            source=config.source_address,
            recipient=recipient["email"],
            subject=subject,
            html_body=wrapped_html,
            unsubscribe_url=unsubscribe_url,
            configuration_set=configuration_set,
        )
        _record_send_result(campaign, log, result)
    except Exception as exc:
        logger.exception("Failed to process recipient %s", recipient["email"])
        RecipientLog.objects.update_or_create(
            campaign=campaign,
            email_address=recipient["email"],
            defaults={
                "member_id": recipient["member_id"],
                "recipient_name": recipient["full_name"],
                "status": "failed",
                "provider": "ses",
                "error_message": str(exc),
            },
        )
        campaign.failed_count += 1


def _record_send_result(campaign, log, result):
    updated = RecipientLog.objects.filter(pk=log.pk, status="pending").update(
        status="failed" if result.error else "sent",
        provider="ses",
        error_message=result.error,
        sent_at=None if result.error else timezone.now(),
        ses_message_id=result.message_id,
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


def _recipient_context(recipient, campaign):
    return {
        "first_name": recipient["first_name"],
        "last_name": recipient["last_name"],
        "full_name": recipient["full_name"],
        "login_link": _build_login_link(recipient["member_id"], campaign),
    }


def _build_login_link(member_id, campaign):
    if not member_id:
        return ""
    token = MagicLoginToken.generate_token()
    MagicLoginToken.objects.create(token=token, member_id=member_id, campaign=campaign)
    frontend_url = getattr(settings, "FRONTEND_URL", "").rstrip("/")
    return f"{frontend_url}/magic-login?token={token}"


def _unsubscribe_url_for(campaign, recipient):
    if not campaign.include_unsubscribe_header or not recipient["member_id"]:
        return ""
    return build_oneclick_unsubscribe_url(recipient["member_id"])


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


def _fail_campaign_for_missing_ses(campaign):
    campaign.status = "failed"
    campaign.error_message = "SES is not configured. Check EmailServiceConfig in admin."
    campaign.save(update_fields=["status", "error_message"])
    raise RuntimeError("SES is not configured. Cannot send campaign.")
