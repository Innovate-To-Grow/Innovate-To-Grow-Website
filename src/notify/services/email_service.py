"""
High-level email service that combines template rendering, layout wrapping,
Gmail account selection, and attachment support into a single function call.

Usage::

    from notify.services.email_service import send_template_email

    success, provider = send_template_email(
        template_key="welcome",
        recipient_email="user@example.com",
        context={"first_name": "Alice"},
        attachments=[("report.pdf", pdf_bytes, "application/pdf")],
    )
"""

import logging
from typing import Any

from notify.providers.email import render_email_layout, send_email

logger = logging.getLogger(__name__)


def send_template_email(
    template_key: str,
    recipient_email: str,
    context: dict[str, Any] | None = None,
    attachments: list[tuple[str, bytes, str]] | None = None,
    gmail_account_id: int | None = None,
    layout_key: str | None = None,
) -> tuple[bool, str]:
    """
    Render an :model:`notify.EmailMessageLayout` by *key* and send it.

    This is the recommended entry point for application code that needs to
    send transactional emails (form confirmations, notifications, etc.).

    Args:
        template_key: ``EmailMessageLayout.key`` to look up.
        recipient_email: Destination email address.
        context: Extra template variables merged with the layout defaults.
        attachments: ``[(filename, content_bytes, mimetype), ...]``
        gmail_account_id: Explicit ``GoogleGmailAccount.pk``.  If ``None``,
            the default active account is used automatically.
        layout_key: Optional ``EmailLayout.key`` to override the layout
            defined on the message template.

    Returns:
        ``(success: bool, provider_name: str)``
    """
    from notify.models import EmailMessageLayout

    # 1. Resolve the email template
    try:
        template = EmailMessageLayout.objects.get(key=template_key, is_active=True)
    except EmailMessageLayout.DoesNotExist:
        logger.error("Email template '%s' not found or inactive", template_key)
        return False, "template_not_found"

    # 2. Render subject + body using the template's own engine
    subject, body, preheader, merged_ctx = template.render(
        context=context,
        recipient_email=recipient_email,
    )

    # 3. Determine which EmailLayout to use
    #    Priority: explicit layout_key > template.layout > default
    effective_layout = template.layout  # may be None
    effective_layout_key = layout_key

    # 4. Wrap with layout to produce final HTML + plain text
    html_body, text_body = render_email_layout(
        subject=subject,
        body=body,
        context=merged_ctx,
        layout=effective_layout if not effective_layout_key else None,
        layout_key=effective_layout_key,
    )

    # 5. Send via the enhanced send_email (which resolves DB accounts)
    #    We pass the already-rendered HTML directly as the body so
    #    send_email does NOT double-render template variables.
    success, provider = send_email(
        target=recipient_email,
        subject=subject,
        body=html_body,
        gmail_account_id=gmail_account_id,
        attachments=attachments,
    )

    if success:
        logger.info(
            "Email '%s' sent to %s via %s",
            template_key,
            recipient_email,
            provider,
        )
    else:
        logger.error(
            "Failed to send email '%s' to %s via %s",
            template_key,
            recipient_email,
            provider,
        )

    return success, provider
