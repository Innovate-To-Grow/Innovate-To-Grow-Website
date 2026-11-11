"""The inbound mail queue: every message the mailbox scan lists, recorded once, for the apps that consume it.

``queue.record`` is called by the bounce processor's scan (``bounces.scanner``) for each listed message; after a scan
recorded new rows, ``queue.notify_consumers`` queues the job of every consumer an app registered
(``registry.register_inbound_consumer``, from its ``AppConfig.ready()``). A consumer drains the rows with ``consume``
(claim, then done / retry / defer / skip), reads the raw headers safely with ``headers``, tells automated mail from a
person's with the pure ``classify`` (rule tables in ``rules``), and removes personal sign-in links with ``scrub``
before storing anything. ``core`` stores metadata only; it never reads or keeps a message body.
"""

from .classify import Evidence, Verdict, auth_summary, classify
from .queue import notify_consumers, pending_count, purge_expired, record
from .registry import active_consumer_kinds, register_inbound_consumer, registered_consumers
from .rules import AUTOMATED, HUMAN, LABELS
from .scrub import LINK_PLACEHOLDER, is_sensitive_url, scrub_links, scrub_subject

__all__ = [
    "AUTOMATED",
    "HUMAN",
    "LABELS",
    "LINK_PLACEHOLDER",
    "Evidence",
    "Verdict",
    "active_consumer_kinds",
    "auth_summary",
    "classify",
    "is_sensitive_url",
    "notify_consumers",
    "pending_count",
    "purge_expired",
    "record",
    "register_inbound_consumer",
    "registered_consumers",
    "scrub_links",
    "scrub_subject",
]
