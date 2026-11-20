"""The sidebar badge of Mail -> Inbox: unread Inbox messages across the accounts that connect, as the background
poller last found them (``apps.mail.services.inbox.health.unread_total``). It never connects to a mailbox."""

import logging

from apps.core.utils.access import user_can_access_app

logger = logging.getLogger(__name__)


def inbox_unread_badge(request) -> str:
    """The unread count for staff who may open the inbox ("" when there is none, or for anyone else)."""
    user = getattr(request, "user", None)
    if user is None or not user_can_access_app(user, "mail"):
        return ""
    try:
        from apps.mail.services.inbox.health import unread_total

        total = unread_total()
    except Exception:
        logger.exception("Could not count the unread inbox messages.")
        return ""
    if total <= 0:
        return ""
    return "99+" if total > 99 else str(total)
