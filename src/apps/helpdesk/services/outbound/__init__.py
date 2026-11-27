"""What the helpdesk sends, and only while shadow mode is off (``tickets.shadow``): replies to the requester and the
acknowledgement of a new ticket. Staff are never emailed (I2G-HELPDESK-01): they work tickets in the admin.
``compose`` writes the emails; ``replies`` and ``acknowledgement`` decide and store them; ``jobs`` sends them from the
background worker."""

from .acknowledgement import queue_acknowledgement
from .compose import fill, reply_subject
from .jobs import register_outbound
from .recipients import cc_suggestions
from .replies import (
    REPLY_MAX_CHARS,
    ReplyCollision,
    ReplyRefused,
    can_reply,
    last_inbound,
    queue_reply,
    site_addresses,
)

__all__ = [
    "REPLY_MAX_CHARS",
    "ReplyCollision",
    "ReplyRefused",
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
