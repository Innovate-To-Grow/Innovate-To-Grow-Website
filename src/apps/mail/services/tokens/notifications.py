"""Durable best-effort subscription confirmation notifications."""

import hashlib
import logging

from django.conf import settings

from apps.authn.models import ContactEmail
from apps.authn.services import email as email_api
from apps.core.services.background_jobs import enqueue_notification_email, jobs_enabled
from apps.core.services.helpers.in_process import start_in_process_task
from apps.core.utils.throttle_cache import throttle_cache

logger = logging.getLogger(__name__)

_ACTIONS = {
    "unsubscribe": ("You've been unsubscribed - Innovate to Grow", "mail/email/unsubscribe_confirmation.html"),
    "resubscribe": ("You've been resubscribed - Innovate to Grow", "mail/email/resubscribe_confirmation.html"),
}

# At most one confirmation per member and action per window. The unsubscribe link is reusable for a year and the
# resubscribe link for an hour, so whoever holds a (forwarded) newsletter link can toggle the flags in a loop; every
# round is a real change, and without this bound each one would mail the member. The flag changes themselves are
# not limited.
CONFIRMATION_WINDOW_SECONDS = 60 * 60


def subscription_confirmation_dedupe_key(action: str, *, member_id, changed_at) -> str:
    """Return the outbox key of the confirmations of one member and action in one window.

    The key names the member, the action and the ``CONFIRMATION_WINDOW_SECONDS`` window the change falls in, not the
    link that caused it: a later real change through the same reusable link is confirmed again in a later window,
    and the outbox's ``get_or_create`` collapses every further change in the same window into the first job.
    """
    if action not in _ACTIONS:
        raise ValueError("Unsupported subscription confirmation action.")
    if changed_at is None:
        raise ValueError("A subscription change needs its change time.")
    window = int(changed_at.timestamp()) // CONFIRMATION_WINDOW_SECONDS
    digest = hashlib.sha256(f"{member_id}|{window}".encode()).hexdigest()
    return f"subscription-confirmation:{action}:{digest}"


def confirmation_recipient(member, email_ids) -> str:
    """The member's primary address, else the oldest of the addresses the change touched."""
    primary_email = member.get_primary_email()
    if primary_email:
        return primary_email
    fallback = (
        ContactEmail.objects.filter(member=member, pk__in=list(email_ids))
        .order_by("created_at")
        .values_list("email_address", flat=True)
        .first()
    )
    return fallback or ""


def send_subscription_confirmation(*, member, action: str, email_ids, changed_at) -> None:
    """Confirm one subscription change; call it only when ``email_ids`` (the rows changed) is non-empty.

    Queues the email in the outbox, with a non-blocking in-process fallback before outbox rollout. Sends at most one
    confirmation per member and action per ``CONFIRMATION_WINDOW_SECONDS`` window.
    """
    if action not in _ACTIONS:
        raise ValueError("Unsupported subscription confirmation action.")
    recipient = confirmation_recipient(member, email_ids)
    if not recipient:
        return

    subject, template = _ACTIONS[action]
    frontend_url = (getattr(settings, "FRONTEND_URL", "") or "").strip().rstrip("/")
    notification = {
        "recipient": recipient,
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
                dedupe_key=subscription_confirmation_dedupe_key(action, member_id=member.pk, changed_at=changed_at),
            )
        except Exception:
            logger.exception("Failed to enqueue subscription confirmation")
        return

    # Without the outbox the window is a per-process marker: it fails open (a restart forgets it), which only
    # costs one more confirmation.
    if not throttle_cache.add(
        f"mail:subscription-confirmation:{action}:{member.pk}", True, CONFIRMATION_WINDOW_SECONDS
    ):
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
