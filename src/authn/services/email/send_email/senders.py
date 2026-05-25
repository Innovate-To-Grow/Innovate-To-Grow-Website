import logging

from django.template.loader import render_to_string

from .actions import render_email_body
from .config import PURPOSE_SUBJECTS

logger = logging.getLogger(__name__)
SES_DELIVERY_ERROR = "Email delivery via AWS SES failed or is not configured."


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

    logger.error("Notification email was not sent: %s", SES_DELIVERY_ERROR)


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

    if email_api._send_via_ses(
        config=config,
        recipient=invitation.email,
        subject=subject,
        html_body=html_body,
    ):
        logger.info("Admin invitation email sent via SES")
        return

    raise RuntimeError(SES_DELIVERY_ERROR)


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

    if email_api._send_via_ses(
        config=config,
        recipient=recipient,
        subject=subject,
        html_body=html_body,
    ):
        logger.info("Verification email sent via SES")
        return

    raise RuntimeError(SES_DELIVERY_ERROR)
