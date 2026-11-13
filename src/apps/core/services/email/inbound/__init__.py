"""The inbound mail queue: every message an Inbox scan lists, recorded once, for the app that consumes it.

``queue.record`` is called by the app that lists the Inbox to fill the queue (the helpdesk's intake, on its own
schedule and checkpoint; bounce processing reads the same Inbox separately and records nothing here). A consumer
drains the rows with ``consume`` (claim, then done / retry / defer / skip), reads the raw headers safely with
``headers``, tells automated mail from a person's with the pure ``classify`` (automatic replies in ``autoreply``, list
and bulk mail in ``bulk``, rule tables in ``rules``), and removes personal sign-in links with ``scrub`` before storing
anything. ``registry`` lets such an app describe its own Inbox scan to the Email Monitoring card. ``core`` stores
metadata only; it never reads or keeps a message body.
"""

from .classify import NO_AUTO_RESPONSE, REPLY_HINT, Evidence, Verdict, auth_summary, classify
from .queue import pending_count, purge_expired, record
from .registry import (
    InboxReader,
    format_interval,
    inbox_readers,
    register_inbox_reader,
    registered_inbox_readers,
)
from .rules import AUTOMATED, HUMAN, LABELS
from .scrub import LINK_PLACEHOLDER, is_sensitive_url, scrub_links, scrub_subject

__all__ = [
    "AUTOMATED",
    "HUMAN",
    "LABELS",
    "LINK_PLACEHOLDER",
    "NO_AUTO_RESPONSE",
    "REPLY_HINT",
    "Evidence",
    "InboxReader",
    "Verdict",
    "auth_summary",
    "classify",
    "format_interval",
    "inbox_readers",
    "is_sensitive_url",
    "pending_count",
    "purge_expired",
    "record",
    "register_inbox_reader",
    "registered_inbox_readers",
    "scrub_links",
    "scrub_subject",
]
