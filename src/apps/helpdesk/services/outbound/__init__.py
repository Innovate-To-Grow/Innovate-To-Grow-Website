"""What the helpdesk sends, and only while shadow mode is off (``tickets.shadow``): replies to the requester, the
acknowledgement of a new ticket, and assignment notifications to staff. ``compose`` writes the emails, ``replies``
and ``notifications`` decide and store them, and ``jobs`` sends them from the background worker."""

from .compose import fill, reply_subject
from .jobs import register_outbound
from .notifications import assignment_changed
from .replies import REPLY_MAX_CHARS, ReplyRefused, can_reply, last_inbound, queue_acknowledgement, queue_reply

__all__ = [
    "REPLY_MAX_CHARS",
    "ReplyRefused",
    "assignment_changed",
    "can_reply",
    "fill",
    "last_inbound",
    "queue_acknowledgement",
    "queue_reply",
    "register_outbound",
    "reply_subject",
]
