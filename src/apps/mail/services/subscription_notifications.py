"""Durable best-effort subscription confirmation notifications."""

import hashlib
import logging

from django.conf import settings

from apps.authn.services import email as email_api
from apps.core.services.background_jobs import enqueue_notification_email, jobs_enabled
from apps.core.services.helpers.in_process import start_in_process_task

logger = logging.getLogger(__name__)


def subscription_confirmation_dedupe_key(action: str, event_token: str) -> str:
    """Return a stable key without persisting the credential-bearing token."""
    if action not in {"unsubscribe", "resubscribe"}:
        raise ValueError("Unsupported subscription confirmation action.")
    if not event_token:
        raise ValueError("A subscription event token is required.")
    digest = hashlib.sha256(event_token.encode("utf-8")).hexdigest()
    return f"subscription-confirmation:{action}:{digest}"


def send_subscription_confirmation(*, member, action: str, event_token: str) -> None:
    """Queue a confirmation, with a non-blocking fallback before outbox rollout."""
    primary_email = member.get_primary_email()
    if not primary_email:
        return

    if action == "unsubscribe":
        subject = "You've been unsubscribed - Innovate to Grow"
        template = "mail/email/unsubscribe_confirmation.html"
    elif action == "resubscribe":
        subject = "You've been resubscribed - Innovate to Grow"
        template = "mail/email/resubscribe_confirmation.html"
    else:
        raise ValueError("Unsupported subscription confirmation action.")

    frontend_url = (getattr(settings, "FRONTEND_URL", "") or "").strip().rstrip("/")
    notification = {
        "recipient": primary_email,
        "subject": subject,
        "template": template,
        "context": {
            "first_name": member.first_name or "there",
            "account_url": f"{frontend_url}/account" if frontend_url else "",
        },
    }

    if jobs_enabled():
        try:
            enqueue_notification_email(
                **notification,
                dedupe_key=subscription_confirmation_dedupe_key(action, event_token),
            )
        except Exception:
            logger.exception("Failed to enqueue subscription confirmation")
        return

    start_in_process_task(
        _send_subscription_notification,
        notification,
        name=f"subscription-confirmation-{action}",
        best_effort_start=True,
    )


def _send_subscription_notification(notification: dict) -> None:
    try:
        email_api.send_notification_email(**notification)
    except Exception:
        logger.exception("Failed to send subscription confirmation")
