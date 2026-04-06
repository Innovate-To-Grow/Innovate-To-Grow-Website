"""
Email delivery service for verification codes.

Uses AWS SES (primary) with Django SMTP fallback.
Credentials are loaded from the EmailServiceConfig singleton in the database.
"""

import logging

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from django.core.mail import EmailMessage
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

PURPOSE_SUBJECTS = {
    "register": "Verify your email - Innovate to Grow",
    "login": "Your login code - Innovate to Grow",
    "password_reset": "Password reset code - Innovate to Grow",
    "password_change": "Password change code - Innovate to Grow",
    "contact_email_verify": "Verify your contact email - Innovate to Grow",
    "admin_login": "Admin login code - Innovate to Grow",
}

PURPOSE_DISPLAY = {
    "register": "verify your email address",
    "login": "sign in to your account",
    "password_reset": "reset your password",
    "password_change": "change your password",
    "contact_email_verify": "verify your contact email",
    "admin_login": "sign in to the admin panel",
}


def _load_config():
    from core.models import EmailServiceConfig

    return EmailServiceConfig.load()


def _render_email_body(*, code: str, purpose: str) -> str:
    return render_to_string(
        "authn/email/verification_code.html",
        {
            "code": code,
            "purpose_display": PURPOSE_DISPLAY.get(purpose, "complete your request"),
            "expiry_minutes": 10,
        },
    )


def _send_via_ses(*, config, recipient: str, subject: str, html_body: str) -> bool:
    """Attempt to send via AWS SES. Returns True on success, False if unconfigured."""
    if not config.ses_configured:
        return False
    try:
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
        return True
    except (BotoCoreError, ClientError):
        logger.exception("SES send failed for %s", recipient)
        return False


def _send_via_smtp(*, config, recipient: str, subject: str, html_body: str):
    """Send via SMTP using DB-stored credentials, bypassing EMAIL_BACKEND setting."""
    from django.core.mail import get_connection

    connection = get_connection(
        backend="django.core.mail.backends.smtp.EmailBackend",
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


def send_verification_email(*, recipient: str, code: str, purpose: str):
    """
    Send a verification code email.

    Tries AWS SES first, falls back to Django SMTP.
    Raises on complete failure so callers can surface AuthChallengeDeliveryError.
    """
    config = _load_config()
    subject = PURPOSE_SUBJECTS.get(purpose, "Your verification code - Innovate to Grow")
    html_body = _render_email_body(code=code, purpose=purpose)

    if _send_via_ses(config=config, recipient=recipient, subject=subject, html_body=html_body):
        logger.info("Verification email sent via SES to %s (purpose=%s)", recipient, purpose)
        return

    logger.info("SES unavailable or failed; falling back to SMTP for %s", recipient)
    _send_via_smtp(config=config, recipient=recipient, subject=subject, html_body=html_body)
    logger.info("Verification email sent via SMTP to %s (purpose=%s)", recipient, purpose)
