"""No-bounce inference: an accepted Microsoft Graph email whose bounce window the scan has provably read shows
"No bounce received" (likely delivered, never proof of it).

Exchange sends a non-delivery report to the message's From address, so the inference holds only for emails sent from
the mailbox the bounce scan reads, with that mailbox as the From address. It covers the emails accepted between
``scanned_since`` (the earliest time the scans have read continuously) and the checkpoint less the scan overlap, the
clock skew and ``no_bounce_after_hours``: their reports would have arrived inside what was read. An email with an
unmatched report received after it was sent (less the clock skew) for its recipient (or naming none) is left unknown: it may be about it.
Only an unknown status moves, in one UPDATE, so a later report still confirms a failure (``store.apply_to_email``).
"""

from datetime import timedelta

from django.conf import settings
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from apps.core.models import EmailBounce, EmailCategory, EmailMonitorState, EmailServiceConfig, OutboundEmail

from ...telemetry import text

DeliveryStatus = OutboundEmail.DeliveryStatus
# Allowance for the clock difference between the site (accepted_at) and Exchange (the report's received time).
_CLOCK_SKEW = timedelta(minutes=10)


def no_bounce_after_hours() -> int:
    """Hours past the send the scan must have read: ``no_bounce_after_hours``, one at least, never above
    ``bounce_match_window_hours`` (a report later than that would not be matched to the email anyway)."""
    config = settings.EMAIL_MONITORING
    return max(1, min(int(config["no_bounce_after_hours"]), int(config["bounce_match_window_hours"])))


def quiet_until(state: EmailMonitorState):
    """The latest accepted time whose bounce window the scans have read, or None while nothing is covered yet."""
    if state.scanned_since is None or state.checkpoint_at is None:
        return None
    overlap = timedelta(seconds=int(settings.EMAIL_MONITORING["bounce_scan_overlap_seconds"]))
    return state.checkpoint_at - overlap - _CLOCK_SKEW - timedelta(hours=no_bounce_after_hours())


def mark_quiet_emails(state: EmailMonitorState) -> int:
    """Move the covered, still unknown Graph emails of ``state.mailbox`` to "No bounce received"; how many moved."""
    if state.paused or not settings.EMAIL_MONITORING["bounce_processing_enabled"]:
        return 0
    until = quiet_until(state)
    if until is None or until < state.scanned_since:
        return 0
    if text.address(EmailServiceConfig.load().from_email) != state.mailbox:
        return 0  # the reports go to another mailbox, which this scan does not read
    # "After" on Exchange's clock: a report it timestamps up to the skew before the site's accepted_at still counts.
    later_unmatched = EmailBounce.objects.filter(
        email__isnull=True, received_at__gte=OuterRef("accepted_at") - _CLOCK_SKEW
    )
    # One recipient: an unmatched report for that recipient, or one in the mailbox naming none (unreadable). Several
    # (only the first is a column): any unmatched report in the mailbox; both are rare and keep the inference safe.
    in_mailbox = later_unmatched.filter(mailbox=state.mailbox)
    same_recipient = later_unmatched.filter(Q(recipient=OuterRef("recipient")) | Q(recipient="", mailbox=state.mailbox))
    emails = (
        OutboundEmail.objects.filter(
            provider="graph",
            status=OutboundEmail.Status.ACCEPTED,
            delivery_status=DeliveryStatus.UNKNOWN,
            mailbox=state.mailbox,
            accepted_at__gte=state.scanned_since,
            accepted_at__lte=until,
        )
        .exclude(category=EmailCategory.ACCESS_CHECK)
        .filter(
            (Q(recipient_count__lte=1) & ~Exists(same_recipient)) | (Q(recipient_count__gt=1) & ~Exists(in_mailbox))
        )
    )
    return emails.update(delivery_status=DeliveryStatus.NO_BOUNCE, updated_at=timezone.now())
