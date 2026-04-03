"""Orchestrate sending an email campaign to all resolved recipients."""

import logging

from django.conf import settings
from django.utils import timezone

from core.models import EmailServiceConfig

from .audience import get_recipients
from .personalize import personalize
from .preview import render_email_html

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
        wrapped_html = render_email_html(body_html)

        log = RecipientLog.objects.create(
            campaign=campaign,
            member_id=recipient["member_id"],
            email_address=recipient["email"],
            recipient_name=recipient["full_name"],
            status="pending",
        )

        provider, error = _send_single(
            config=config, recipient=recipient["email"], subject=subject, html_body=wrapped_html
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


def _send_single(*, config, recipient, subject, html_body):
    """
    Try SES first, fall back to SMTP. Returns (provider, error_message).
    On success error_message is empty string.
    """
    # Try SES
    if config.ses_configured:
        try:
            import boto3

            client = boto3.client(
                "ses",
                region_name=config.ses_region,
                aws_access_key_id=config.ses_access_key_id,
                aws_secret_access_key=config.ses_secret_access_key,
            )
            client.send_email(
                Destination={"ToAddresses": [recipient]},
                Message={
                    "Body": {"Html": {"Charset": "UTF-8", "Data": html_body}},
                    "Subject": {"Charset": "UTF-8", "Data": subject},
                },
                Source=config.source_address,
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
        )
        msg.content_subtype = "html"
        msg.send()
        return "smtp", ""
    except Exception as exc:
        logger.exception("SMTP send failed for %s", recipient)
        return "smtp", str(exc)
