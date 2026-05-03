"""
Email delivery service for verification codes.

Uses AWS SES (primary) with Django SMTP fallback.
Credentials are loaded from the EmailServiceConfig singleton in the database.
"""

import logging
import time
from urllib.parse import urlencode

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

_SMTP_TIMEOUT = 15  # seconds
_SMTP_MAX_RETRIES = 2

PURPOSE_SUBJECTS = {
    "register": "Verify your email - Innovate to Grow",
    "login": "Your login code - Innovate to Grow",
    "password_reset": "Password reset code - Innovate to Grow",
    "password_change": "Password change code - Innovate to Grow",
    "account_delete": "Delete account code - Innovate to Grow",
    "contact_email_verify": "Verify your contact email - Innovate to Grow",
    "admin_login": "Admin login code - Innovate to Grow",
}

PURPOSE_DISPLAY = {
    "register": "verify your email address",
    "login": "sign in to your account",
    "password_reset": "reset your password",
    "password_change": "change your password",
    "account_delete": "delete your account",
    "contact_email_verify": "verify your contact email",
    "admin_login": "sign in to the admin panel",
}

PUBLIC_LINK_LABELS = {
    "login": "Sign In to Your Account",
    "subscribe": "Continue to Newsletter",
    "event_registration": "Continue to Event Registration",
    "register": "Continue Registration",
}
PUBLIC_LINK_DESCRIPTIONS = {
    "login": "Use this secure link within the next 10 minutes to sign in instantly.",
    "subscribe": "Use this secure link within the next 10 minutes to continue with your newsletter access.",
    "event_registration": "Use this secure link within the next 10 minutes to continue with event registration.",
    "register": "Use this secure link within the next 10 minutes to continue setting up your account.",
}


def _load_config():
    from core.models import EmailServiceConfig

    return EmailServiceConfig.load()


def _build_email_action(*, recipient: str, code: str, purpose: str, link_flow: str | None, link_source: str | None):
    frontend_url = (getattr(settings, "FRONTEND_URL", "") or "").strip().rstrip("/")
    normalized_email = (recipient or "").strip().lower()
    if (
        purpose not in {"register", "login"}
        or link_flow not in {"auth", "login", "register"}
        or link_source not in PUBLIC_LINK_LABELS
        or not frontend_url
        or not normalized_email
    ):
        return {"url": "", "label": "", "description": ""}

    params = urlencode(
        {
            "flow": link_flow,
            "source": link_source,
            "email": normalized_email,
            "code": code,
        }
    )
    return {
        "url": f"{frontend_url}/email-auth-link?{params}",
        "label": PUBLIC_LINK_LABELS[link_source],
        "description": PUBLIC_LINK_DESCRIPTIONS[link_source],
    }


def _render_email_body(
    *,
    recipient: str,
    code: str,
    purpose: str,
    link_flow: str | None = None,
    link_source: str | None = None,
) -> str:
    action = _build_email_action(
        recipient=recipient,
        code=code,
        purpose=purpose,
        link_flow=link_flow,
        link_source=link_source,
    )
    return render_to_string(
        "authn/email/verification_code.html",
        {
            "code": code,
            "purpose_display": PURPOSE_DISPLAY.get(purpose, "complete your request"),
            "expiry_minutes": 10,
            "action_url": action["url"],
            "action_label": action["label"],
            "action_description": action["description"],
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
        logger.exception("SES send failed while sending email")
        return False


def _send_via_smtp(*, config, recipient: str, subject: str, html_body: str):
    """Send via SMTP using DB-stored credentials, bypassing EMAIL_BACKEND setting.

    Retries once on transient connection failures (timeout, reset, DNS).
    """
    from django.core.mail import get_connection

    last_exc = None
    for attempt in range(1, _SMTP_MAX_RETRIES + 1):
        try:
            connection = get_connection(
                backend="django.core.mail.backends.smtp.EmailBackend",
                host=config.smtp_host,
                port=config.smtp_port,
                username=config.smtp_username,
                password=config.smtp_password,
                use_tls=config.smtp_use_tls,
                fail_silently=False,
                timeout=_SMTP_TIMEOUT,
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
            return
        except Exception as exc:
            last_exc = exc
            logger.warning("SMTP attempt %d/%d failed.", attempt, _SMTP_MAX_RETRIES, exc_info=True)
            if attempt < _SMTP_MAX_RETRIES:
                time.sleep(1)
    raise last_exc


def send_notification_email(*, recipient: str, subject: str, template: str, context: dict):
    """
    Send an informational (non-code) notification email.

    Uses SES primary, SMTP fallback. Best-effort: logs but does not raise on failure.
    """
    config = _load_config()
    html_body = render_to_string(template, context)

    if _send_via_ses(config=config, recipient=recipient, subject=subject, html_body=html_body):
        logger.info("Notification email sent via SES")
        return

    logger.info("SES unavailable; falling back to SMTP for notification email")
    try:
        _send_via_smtp(config=config, recipient=recipient, subject=subject, html_body=html_body)
        logger.info("Notification email sent via SMTP")
    except Exception:
        logger.exception("Failed to send notification email")


def send_verification_email(
    *,
    recipient: str,
    code: str,
    purpose: str,
    link_flow: str | None = None,
    link_source: str | None = None,
):
    """
    Send a verification code email.

    Tries AWS SES first, falls back to Django SMTP.
    Raises on complete failure so callers can surface AuthChallengeDeliveryError.
    """
    config = _load_config()
    subject = PURPOSE_SUBJECTS.get(purpose, "Your verification code - Innovate to Grow")
    html_body = _render_email_body(
        recipient=recipient,
        code=code,
        purpose=purpose,
        link_flow=link_flow,
        link_source=link_source,
    )

    if not config.ses_configured:
        logger.info(
            "SES not configured; sending verification email via SMTP (host=%s)",
            config.smtp_host,
        )
    elif _send_via_ses(config=config, recipient=recipient, subject=subject, html_body=html_body):
        logger.info("Verification email sent via SES")
        return
    else:
        logger.warning("SES send failed; falling back to SMTP (host=%s)", config.smtp_host)

    _send_via_smtp(config=config, recipient=recipient, subject=subject, html_body=html_body)
    logger.info("Verification email sent via SMTP")
