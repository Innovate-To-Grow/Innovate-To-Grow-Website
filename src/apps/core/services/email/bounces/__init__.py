"""Bounce processing: non-delivery reports (NDRs) and delivery status notifications (DSNs) in the Microsoft Graph
sending mailbox, read-only, matched to the outgoing emails the telemetry recorded.

Microsoft Graph's ``202 Accepted`` only means a message was queued; a later failure comes back as a report in the
sending mailbox. ``source`` names the mailbox and the report candidates, ``scanner`` reads them incrementally
(``state`` holds its checkpoint, lease and health), ``dsn`` parses them, ``classify`` grades each recipient (hard,
soft, rejected, delayed, unknown), ``matching`` finds the email a report is about only on a reliable identifier, and
``store`` saves each bounce once. ``jobs`` runs the scans in the background worker.
"""

from .jobs import BOUNCE_SCAN_JOB_KIND, ensure_scheduled, purge_finished_jobs, register_bounce_jobs, run_now
from .scanner import ScanOutcome, scan_mailbox
from .source import active_reader

__all__ = [
    "BOUNCE_SCAN_JOB_KIND",
    "ScanOutcome",
    "active_reader",
    "ensure_scheduled",
    "purge_finished_jobs",
    "register_bounce_jobs",
    "run_now",
    "scan_mailbox",
]
