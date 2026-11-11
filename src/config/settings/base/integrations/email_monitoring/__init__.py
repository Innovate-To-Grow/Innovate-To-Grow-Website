"""
Email monitoring: telemetry of every outgoing email (the delivery facade records each logical email and each
provider attempt) and the processing of bounce notifications (NDRs / DSNs) that arrive in the Microsoft Graph
sending mailbox.

Every value is an app default (nothing documents them); each comment says what it does. The switches and the
mailbox allow-list can be set from the environment; the operational pause of bounce processing is on the dashboard
(Mail → Delivery Operations → Email Monitoring), stored with the bounce processor's state.
"""

import os

from django.core.exceptions import ImproperlyConfigured


def _env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name, "").strip().lower()
    if not value:
        return default
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ImproperlyConfigured(f"{name} must be true or false.")


def _env_mailboxes(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    return tuple(item.strip().lower() for item in value.split(",") if item.strip())


EMAIL_MONITORING = {
    # Record every outgoing email and provider attempt. A kill switch only: off, the dashboard shows no new data.
    "telemetry_enabled": _env_flag("EMAIL_TELEMETRY_ENABLED", True),
    # Keep each email's subject (truncated to 255 characters) for the log. Off: only a SHA-256 digest of it is
    # kept, which bounce matching still uses.
    "store_subjects": _env_flag("EMAIL_TELEMETRY_STORE_SUBJECTS", True),
    # Days an outgoing email (with its attempts) is kept, and days a bounce notification record is kept.
    "retention_days": 180,
    "bounce_retention_days": 365,
    # Rows deleted per statement by the retention purge (the worker's hourly maintenance).
    "purge_batch_size": 1000,
    # An attempt still "in progress" after this long was interrupted (a worker stopped mid-send): the log shows it
    # as outcome unknown.
    "attempt_stale_seconds": 900,
    # Bounce processing reads only these mailboxes, and only while the Graph mailbox scope also grants read on them.
    "bounce_mailboxes": _env_mailboxes("EMAIL_BOUNCE_MAILBOXES", ("i2g@ucmerced.edu",)),
    "bounce_processing_enabled": _env_flag("EMAIL_BOUNCE_PROCESSING_ENABLED", True),
    # Seconds between two scans of the mailbox (a Retry-After from Microsoft can only lengthen it).
    "bounce_scan_interval_seconds": 600,
    # The shorter interval used while an inbound-mail consumer (the helpdesk) is switched on: every message the scan
    # lists is recorded in the inbound queue, and a ticket queue wants new mail within minutes. A quiet scan is one
    # list request, about 720 a day at 120 seconds; Outlook allows 10,000 requests per 10 minutes per app and mailbox.
    "inbox_scan_interval_seconds": 120,
    # Days an inbound queue row (metadata of one listed message) is kept after it was processed, or recorded when it
    # never was (not received: a rescan records old mail, which must still wait to be imported). What a consumer made
    # of it (a helpdesk ticket) has its own retention.
    "inbound_retention_days": 90,
    # Ask Microsoft Graph for immutable message ids (Prefer: IdType="ImmutableId"), which survive a move to another
    # Outlook folder. Off by default: switching changes the ids the bounce scan and the Admin Inbox see once (the
    # bounce records and the inbound queue still de-duplicate through the internet Message-ID).
    "graph_immutable_ids": _env_flag("EMAIL_GRAPH_IMMUTABLE_IDS", False),
    # Messages listed per request, list requests per scan, and NDR candidates opened (raw MIME) per scan.
    "bounce_scan_page_size": 50,
    "bounce_scan_max_pages": 10,
    "bounce_scan_max_messages": 200,
    # A scan stops (keeping its progress) after this many seconds: it shares the background worker with every
    # queued email, so a flood of reports must never hold that worker for long.
    "bounce_scan_max_seconds": 60,
    # Recipients read from one report: a report about the site's own mail names at most a message's recipients
    # (500 for Graph), so more only comes from a forged one.
    "bounce_max_recipients_per_report": 50,
    # Each scan starts this far before its checkpoint, so a message filed late is not missed (duplicates are skipped).
    "bounce_scan_overlap_seconds": 900,
    # The first scan of a mailbox looks back this far, unless staff set another lookback for the mailbox on the
    # dashboard (within one hour and bounce_max_lookback_days).
    "bounce_initial_lookback_hours": 72,
    # The furthest back a scan can be sent, in days: "Rescan since" accepts no earlier time, and no first-scan lookback
    # is longer. It never exceeds bounce_retention_days (older reports would be purged within the hour). It bounds those
    # two admin controls, so it is set here rather than beside them.
    "bounce_max_lookback_days": 90,
    # Most of one NDR's raw MIME read; the delivery-status part comes first, so a longer one is parsed as far as read.
    "bounce_message_max_bytes": 256 * 1024,
    # A scan holds the mailbox for at most this long, so a stopped worker never blocks the next scan for good.
    "bounce_lease_seconds": 900,
    # A bounce without the original Message-ID is matched to an email sent to the same recipient with the same
    # subject in this window before it, and only when exactly one such email exists.
    "bounce_match_window_hours": 120,
    # How a message is recognised as a bounce candidate before its MIME is read (case-insensitive): a subject
    # prefix, or a sender whose local part is one of these (or starts with "microsoftexchange", Exchange's NDR sender).
    "ndr_subject_prefixes": (
        "undeliverable:",
        "undelivered mail returned to sender",
        "undeliverable mail",
        "delivery status notification",
        "delivery has failed",
        "delivery failure",
        "mail delivery failed",
        "mail delivery failure",
        "mail delivery system",
        "returned mail",
        "failure notice",
        "non-delivery",
        "message not delivered",
        "delivery delayed",
        "delayed:",
        "warning: could not send message",
    ),
    "ndr_sender_local_parts": ("postmaster", "mailer-daemon", "mail-daemon", "maildaemon"),
}
