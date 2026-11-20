"""What the helpdesk sends, and only while shadow mode is off (``tickets.shadow``): replies to the requester, the
acknowledgement of a new ticket, and assignment notifications to staff. ``compose`` writes the emails; ``replies``,
``acknowledgement`` and ``notifications`` decide and store them; ``jobs`` (and the notice job in ``notifications``)
send them from the background worker."""

from .acknowledgement import queue_acknowledgement
from .compose import fill, reply_subject
from .jobs import register_outbound
from .notifications import assignment_changed
from .recipients import cc_suggestions
from .replies import (
    REPLY_MAX_CHARS,
    ReplyRefused,
    can_reply,
    last_inbound,
    queue_reply,
    site_addresses,
)

__all__ = [
    "REPLY_MAX_CHARS",
    "ReplyRefused",
    "assignment_changed",
    "can_reply",
    "cc_suggestions",
    "fill",
    "last_inbound",
    "queue_acknowledgement",
    "queue_reply",
    "register_outbound",
    "reply_subject",
    "site_addresses",
]
