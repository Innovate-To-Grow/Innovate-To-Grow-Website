"""Orchestrate sending an email campaign to all resolved recipients."""

import logging
import time
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from django.conf import settings
from django.utils import timezone

from core.models import EmailServiceConfig

from .audience import get_recipients
from .personalize import personalize
from .preview import render_email_html
from .unsubscribe_token import build_oneclick_unsubscribe_url

logger = logging.getLogger(__name__)


@dataclass
class SesSendResult:
    """Outcome of a single SES send_raw_email call."""

    message_id: str = ""
    error: str = ""


def _build_login_link(member_id, campaign):
    """Create a MagicLoginToken and return the frontend magic-login URL."""
    if not member_id:
        return ""
    from mail.models import MagicLoginToken

    token = MagicLoginToken.generate_token()
    MagicLoginToken.objects.create(token=token, member_id=member_id, campaign=campaign)
    frontend_url = getattr(settings, "FRONTEND_URL", "").rstrip("/")
    return f"{frontend_url}/magic-login?token={token}"


def _build_unsubscribe_url(member_id):
    """Generate the RFC 8058 one-click unsubscribe URL (for email headers)."""
    if not member_id:
        return ""
    return build_oneclick_unsubscribe_url(member_id)


def send_campaign(campaign, sent_by):
    """
    Send *campaign* to all resolved recipients via SES.

    Returns a summary dict: ``{"total": int, "sent": int, "failed": int}``.
    """
    config = EmailServiceConfig.load()
    recipients = get_recipients(campaign)

    campaign.status = "sending"
    campaign.sent_by = sent_by
    campaign.total_recipients = len(recipients)
    campaign.sent_count = 0
    campaign.failed_count = 0
    campaign.error_message = ""
    campaign.save(
        update_fields=["status", "sent_by", "total_recipients", "sent_count", "failed_count", "error_message"]
    )

    ses_client = _get_ses_client(config)
    if ses_client is None:
        campaign.status = "failed"
        campaign.error_message = "SES is not configured. Check EmailServiceConfig in admin."
        campaign.save(update_fields=["status", "error_message"])
        raise RuntimeError("SES is not configured. Cannot send campaign.")

    send_rate = config.ses_max_send_rate or 0
    min_interval = (1.0 / send_rate) if send_rate > 0 else 0
    last_send_time = 0.0

    configuration_set = _get_configuration_set_name(config)
    if not configuration_set:
        logger.warning(
            "No SES configuration set configured; bounce/complaint tracking disabled for campaign %s",
            campaign.pk,
        )

    from mail.models import RecipientLog

    for recipient in recipients:
        # Rate-limit: wait if we're sending faster than the configured rate
        if min_interval > 0 and last_send_time > 0:
            elapsed = time.monotonic() - last_send_time
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)

        try:
            login_link = _build_login_link(recipient["member_id"], campaign)
            context = {
                "first_name": recipient["first_name"],
                "last_name": recipient["last_name"],
                "full_name": recipient["full_name"],
                "login_link": login_link,
            }
            subject = personalize(campaign.subject, context)
            body_html = personalize(campaign.body, context)

            unsubscribe_url = (
                _build_unsubscribe_url(recipient["member_id"]) if campaign.include_unsubscribe_header else ""
            )
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
            last_send_time = time.monotonic()

            # Conditional update on status="pending" so an SNS event that
            # lands between create() and this write keeps its terminal state.
            updated = RecipientLog.objects.filter(pk=log.pk, status="pending").update(
                status="failed" if result.error else "sent",
                provider="ses",
                error_message=result.error,
                sent_at=None if result.error else timezone.now(),
                ses_message_id=result.message_id,
            )
            if updated == 0:
                # A webhook beat us; keep whatever terminal state it wrote.
                log.refresh_from_db()
                if log.status in {"bounced", "complained", "rejected", "failed"}:
                    campaign.failed_count += 1
                else:
                    campaign.sent_count += 1
            elif result.error:
                campaign.failed_count += 1
            else:
                campaign.sent_count += 1
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

        # Save progress every 10 recipients so the admin poller can observe
        # live updates without the per-iteration write amplification.
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


def _get_ses_client(config):
    """Create a reusable boto3 SES client, or None if SES is not configured."""
    if not config.ses_configured:
        return None
    try:
        import boto3

        return boto3.client(
            "ses",
            region_name=config.ses_region,
            aws_access_key_id=config.ses_access_key_id,
            aws_secret_access_key=config.ses_secret_access_key,
        )
    except Exception:
        logger.exception("Failed to create SES client")
        return None


def _get_configuration_set_name(config: EmailServiceConfig) -> str:
    """Return the SES Configuration Set name to tag on outbound sends.

    Prefers a future per-config override; falls back to the global
    SES_CONFIGURATION_SET_NAME env setting. Empty string means "unset" —
    in that case ConfigurationSetName is omitted from the SES call
    (SES rejects empty strings).
    """
    name = getattr(config, "ses_configuration_set_name", "") or ""
    if not name:
        name = getattr(settings, "SES_CONFIGURATION_SET_NAME", "") or ""
    return name.strip()


def _build_unsubscribe_headers(unsubscribe_url):
    """Return a dict of RFC 8058 List-Unsubscribe headers, or empty dict."""
    if not unsubscribe_url:
        return {}
    return {
        "List-Unsubscribe": f"<{unsubscribe_url}>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }


def _build_raw_ses_message(*, source, recipient, subject, html_body, extra_headers):
    """Build a MIME message suitable for SES send_raw_email."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = source
    msg["To"] = recipient
    for key, value in extra_headers.items():
        msg[key] = value
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    return msg.as_string()


def _send_via_ses(
    *, ses_client, source, recipient, subject, html_body, unsubscribe_url="", configuration_set=""
) -> SesSendResult:
    """Send a single email via SES.

    Returns a ``SesSendResult`` carrying either the SES ``MessageId`` (needed
    later to correlate SNS bounce/complaint/delivery events) or an error string
    from a synchronous failure.
    """
    unsub_headers = _build_unsubscribe_headers(unsubscribe_url)
    try:
        raw_message = _build_raw_ses_message(
            source=source,
            recipient=recipient,
            subject=subject,
            html_body=html_body,
            extra_headers=unsub_headers,
        )
        kwargs = {
            "Source": source,
            "Destinations": [recipient],
            "RawMessage": {"Data": raw_message},
        }
        if configuration_set:
            kwargs["ConfigurationSetName"] = configuration_set
        response = ses_client.send_raw_email(**kwargs)
        return SesSendResult(message_id=response.get("MessageId", ""))
    except Exception as exc:
        logger.exception("SES send failed for %s", recipient)
        return SesSendResult(error=str(exc))
