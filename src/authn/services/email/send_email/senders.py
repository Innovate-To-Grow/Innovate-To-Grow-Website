import logging

from django.template.loader import render_to_string

from .actions import render_email_body
from .config import PURPOSE_SUBJECTS

logger = logging.getLogger(__name__)


def send_notification_email(*, recipient: str, subject: str, template: str, context: dict):
    import authn.services.email.send_email as email_api

    config = email_api._load_config()
    html_body = render_to_string(template, context)

    if email_api._send_via_ses(
        config=config,
        recipient=recipient,
        subject=subject,
        html_body=html_body,
    ):
        logger.info("Notification email sent via SES")
        return

    logger.info("SES unavailable; falling back to SMTP for notification email")
    try:
        email_api._send_via_smtp(
            config=config,
            recipient=recipient,
            subject=subject,
            html_body=html_body,
        )
        logger.info("Notification email sent via SMTP")
    except Exception:
        logger.exception("Failed to send notification email")


def send_admin_invitation_email(*, invitation, request=None):
    import authn.services.email.send_email as email_api

    config = email_api._load_config()
    subject = "You're invited to join Innovate to Grow Admin"
    html_body = render_to_string(
        "authn/email/admin_invitation.html",
        {
            "acceptance_url": invitation.get_acceptance_url(request),
            "expires_at": invitation.expires_at,
            "invited_by": invitation.invited_by,
            "message": invitation.message,
            "role": invitation.get_role_display(),
        },
    )

    if not config.ses_configured:
        logger.info(
            "SES not configured; sending admin invitation via SMTP (host=%s)",
            config.smtp_host,
        )
    elif email_api._send_via_ses(
        config=config,
        recipient=invitation.email,
        subject=subject,
        html_body=html_body,
    ):
        logger.info("Admin invitation email sent via SES")
        return
    else:
        logger.warning(
            "SES send failed; falling back to SMTP for admin invitation (host=%s)",
            config.smtp_host,
        )

    email_api._send_via_smtp(
        config=config,
        recipient=invitation.email,
        subject=subject,
        html_body=html_body,
    )
    logger.info("Admin invitation email sent via SMTP")


def send_verification_email(
    *,
    recipient: str,
    code: str,
    purpose: str,
    link_flow: str | None = None,
    link_source: str | None = None,
):
    import authn.services.email.send_email as email_api

    config = email_api._load_config()
    subject = PURPOSE_SUBJECTS.get(
        purpose,
        "Your verification code - Innovate to Grow",
    )
    html_body = render_email_body(
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
    elif email_api._send_via_ses(
        config=config,
        recipient=recipient,
        subject=subject,
        html_body=html_body,
    ):
        logger.info("Verification email sent via SES")
        return
    else:
        logger.warning(
            "SES send failed; falling back to SMTP (host=%s)",
            config.smtp_host,
        )

    email_api._send_via_smtp(
        config=config,
        recipient=recipient,
        subject=subject,
        html_body=html_body,
    )
    logger.info("Verification email sent via SMTP")
