import logging
import time

from django.utils import timezone

from apps.core.models import EmailServiceConfig
from apps.mail.models import RecipientLog
from apps.mail.services.tokens.login_links import issue_login_link

from ..audience import get_recipients
from ..campaign.personalize import personalize
from ..campaign.preview import render_email_html
from ..tokens.unsubscribe import build_oneclick_unsubscribe_url
from .transport import SesSendResult, _get_configuration_set_name, _get_ses_client, _send_via_ses

logger = logging.getLogger(__name__)


def send_campaign(campaign, sent_by):
    recipients = get_recipients(campaign)
    _mark_campaign_sending(campaign, sent_by, len(recipients))
    logs = RecipientLog.objects.bulk_create(
        [
            RecipientLog(
                campaign=campaign,
                member_id=recipient["member_id"],
                email_address=recipient["email"],
                recipient_name=recipient["full_name"],
                attempts=1,
            )
            for recipient in recipients
        ]
    )
    if not recipients:
        return _finalize_campaign(campaign)

    config = EmailServiceConfig.load()
    ses_client = _get_ses_client(config)
    if ses_client is None:
        _fail_campaign_for_missing_delivery_config(campaign, recipients)

    send_timing = SendTiming(config.max_send_rate or 0)
    configuration_set = _get_configuration_set_name(config)
    if ses_client is not None and not configuration_set:
        logger.warning(
            "No SES configuration set configured; bounce/complaint tracking disabled for campaign %s",
            campaign.pk,
        )

    for index, (recipient, log) in enumerate(zip(recipients, logs, strict=True), start=1):
        send_timing.wait_if_needed()
        _send_one_recipient(campaign, config, ses_client, configuration_set, recipient, log=log)
        send_timing.mark_sent()
        if index % 10 == 0:
            _refresh_campaign_progress(campaign)

    return _finalize_campaign(campaign)


def _finalize_campaign(campaign):
    _refresh_campaign_progress(campaign)
    return {
        "total": campaign.total_recipients,
        "sent": campaign.sent_count,
        "failed": campaign.failed_count,
    }


def _refresh_campaign_progress(campaign):
    from apps.mail.services.campaign.dispatch import aggregate_email_campaign

    # SES callbacks update the same rows while this loop is running. Always
    # derive progress from persisted logs instead of overwriting their counts.
    aggregate_email_campaign(campaign.pk)
    campaign.refresh_from_db(
        fields=["status", "total_recipients", "sent_count", "failed_count", "sent_at", "error_message"]
    )


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


def _send_one_recipient(campaign, config, ses_client, configuration_set, recipient, *, log=None):
    try:
        if log is None:
            log = RecipientLog.objects.create(
                campaign=campaign,
                member_id=recipient["member_id"],
                email_address=recipient["email"],
                recipient_name=recipient["full_name"],
                attempts=1,
            )
        context = _recipient_context(recipient, campaign)
        subject = personalize(campaign.subject, context)
        body_html = personalize(campaign.body, context)
        unsubscribe_url = _unsubscribe_url_for(campaign, recipient)
        wrapped_html = render_email_html(body_html, unsubscribe_url=unsubscribe_url)
        result = _send_with_configured_provider(
            config=config,
            ses_client=ses_client,
            configuration_set=configuration_set,
            recipient=recipient["email"],
            subject=subject,
            wrapped_html=wrapped_html,
            unsubscribe_url=unsubscribe_url,
            recipient_log_id=log.pk,
            delivery_attempt=log.attempts,
        )
        _record_send_result(campaign, log, result)
    except Exception as exc:
        logger.exception("Failed to process recipient %s", recipient["email"])
        RecipientLog.objects.filter(
            campaign=campaign,
            email_address=recipient["email"],
            status="pending",
        ).update(
            status="failed",
            provider=_configured_provider(config),
            error_message=str(exc),
        )
        campaign.failed_count += 1


def _send_with_configured_provider(
    *,
    config,
    ses_client,
    configuration_set,
    recipient,
    subject,
    wrapped_html,
    unsubscribe_url,
    recipient_log_id=None,
    delivery_attempt=0,
):
    if ses_client is not None:
        return _send_via_ses(
            ses_client=ses_client,
            source=config.source_address,
            recipient=recipient,
            subject=subject,
            html_body=wrapped_html,
            unsubscribe_url=unsubscribe_url,
            configuration_set=configuration_set,
            recipient_log_id=recipient_log_id,
            delivery_attempt=delivery_attempt,
        )
    return SesSendResult(provider="", error="Email delivery is not configured.")


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
    return issue_login_link(
        member_id=member_id,
        campaign=campaign,
        validity_days=campaign.login_link_validity_days,
    )


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


def _fail_campaign_for_missing_delivery_config(campaign, recipients):
    error_message = "Email delivery is not configured. Check Notification Delivery in admin."
    for recipient in recipients:
        RecipientLog.objects.update_or_create(
            campaign=campaign,
            email_address=recipient["email"],
            defaults={
                "member_id": recipient["member_id"],
                "recipient_name": recipient["full_name"],
                "status": "failed",
                "provider": "",
                "error_message": error_message,
            },
        )
    campaign.status = "failed"
    campaign.failed_count = len(recipients)
    campaign.error_message = error_message
    campaign.save(update_fields=["status", "failed_count", "error_message"])
    raise RuntimeError("Email delivery is not configured. Cannot send campaign.")
