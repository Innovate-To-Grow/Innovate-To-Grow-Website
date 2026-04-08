"""Orchestrate sending an email campaign to all resolved recipients."""

import logging
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
    Send *campaign* to all resolved recipients.

    Returns a summary dict: ``{"total": int, "sent": int, "failed": int}``.
    """
    config = EmailServiceConfig.load()
    recipients = get_recipients(campaign)

    campaign.status = "sending"
    campaign.sent_by = sent_by
    campaign.total_recipients = len(recipients)
    campaign.sent_count = 0
    campaign.failed_count = 0
    campaign.save(update_fields=["status", "sent_by", "total_recipients", "sent_count", "failed_count"])

    from mail.models import RecipientLog

    for recipient in recipients:
        login_link = _build_login_link(recipient["member_id"], campaign)
        context = {
            "first_name": recipient["first_name"],
            "last_name": recipient["last_name"],
            "full_name": recipient["full_name"],
            "login_link": login_link,
        }
        subject = personalize(campaign.subject, context)
        body_html = personalize(campaign.body, context)

        unsubscribe_url = _build_unsubscribe_url(recipient["member_id"]) if campaign.include_unsubscribe_header else ""
        wrapped_html = render_email_html(body_html, unsubscribe_url=unsubscribe_url)

        log = RecipientLog.objects.create(
            campaign=campaign,
            member_id=recipient["member_id"],
            email_address=recipient["email"],
            recipient_name=recipient["full_name"],
            status="pending",
        )

        provider, error = _send_single(
            config=config,
            recipient=recipient["email"],
            subject=subject,
            html_body=wrapped_html,
            unsubscribe_url=unsubscribe_url,
        )
        if error:
            log.status = "failed"
            log.error_message = error
            campaign.failed_count += 1
        else:
            log.status = "sent"
            log.sent_at = timezone.now()
            campaign.sent_count += 1
        log.provider = provider
        log.save(update_fields=["status", "provider", "error_message", "sent_at"])

    campaign.status = "sent" if campaign.failed_count < campaign.total_recipients else "failed"
    campaign.sent_at = timezone.now()
    campaign.save(update_fields=["status", "sent_count", "failed_count", "sent_at"])

    return {
        "total": campaign.total_recipients,
        "sent": campaign.sent_count,
        "failed": campaign.failed_count,
    }


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


def _send_single(*, config, recipient, subject, html_body, unsubscribe_url=""):
    """
    Try SES first, fall back to SMTP. Returns (provider, error_message).
    On success error_message is empty string.
    """
    unsub_headers = _build_unsubscribe_headers(unsubscribe_url)

    # Try SES (raw email to support custom headers)
    if config.ses_configured:
        try:
            import boto3

            client = boto3.client(
                "ses",
                region_name=config.ses_region,
                aws_access_key_id=config.ses_access_key_id,
                aws_secret_access_key=config.ses_secret_access_key,
            )
            raw_message = _build_raw_ses_message(
                source=config.source_address,
                recipient=recipient,
                subject=subject,
                html_body=html_body,
                extra_headers=unsub_headers,
            )
            client.send_raw_email(
                Source=config.source_address,
                Destinations=[recipient],
                RawMessage={"Data": raw_message},
            )
            return "ses", ""
        except Exception:
            logger.exception("SES send failed for %s", recipient)

    # Fall back to SMTP
    try:
        from django.core.mail import EmailMessage, get_connection

        connection = get_connection(
            host=config.smtp_host,
            port=config.smtp_port,
            username=config.smtp_username,
            password=config.smtp_password,
            use_tls=config.smtp_use_tls,
            fail_silently=False,
        )
        msg = EmailMessage(
            subject=subject,
            body=html_body,
            from_email=config.source_address,
            to=[recipient],
            connection=connection,
            headers=unsub_headers,
        )
        msg.content_subtype = "html"
        msg.send()
        return "smtp", ""
    except Exception as exc:
        logger.exception("SMTP send failed for %s", recipient)
        return "smtp", str(exc)
