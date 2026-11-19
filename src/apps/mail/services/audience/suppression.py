"""Bulk campaign holds from staff decisions, trusted address failures and signed SES events."""

from django.db.models import Q
from django.db.models.functions import Lower

from apps.core.services.email.telemetry import text
from apps.mail.models import BouncedAddress, RecipientLog
from apps.mail.services.email_monitoring.addresses.policies.graph import graph_hold_addresses

SKIPPED_MESSAGE = "Not sent: this address is suppressed for bulk mail (Email Monitoring → Bounced addresses)."


class CampaignAddressHeld(Exception):
    """The address became ineligible after the recipient was queued or admitted to the bulk lane."""


def normalize_address(value) -> str:
    """The bare, lower-case address of value, or an empty string when it holds none."""
    return text.address(value)


def suppressed_addresses(addresses=None) -> frozenset[str]:
    """Return campaign holds, including events received since the last aggregation."""
    rows = BouncedAddress.objects.filter(
        Q(suppressed_at__isnull=False) | Q(complaint_count__gt=0) | Q(ses_permanent_count__gt=0)
    ).order_by()
    events = (
        RecipientLog.objects.filter(
            Q(complained_at__isnull=False) | Q(bounced_at__isnull=False, bounce_type__iexact="permanent")
        )
        .annotate(address=Lower("email_address"))
        .order_by()
    )
    if addresses is not None:
        rows = rows.filter(address__in=addresses)
        events = events.filter(address__in=addresses)
    holds = graph_hold_addresses(addresses).union(
        rows.values_list("address", flat=True), events.values_list("address", flat=True)
    )
    return frozenset(holds)


def is_suppressed(address) -> bool:
    normalized = normalize_address(address)
    return bool(normalized and suppressed_addresses([normalized]))


def check_before_delivery(address) -> None:
    if is_suppressed(address):
        raise CampaignAddressHeld


def split_suppressed(recipients, *, key: str = "email") -> tuple[list, list]:
    """Split an audience once, without querying individually for each recipient."""
    blocked = suppressed_addresses()
    kept, skipped = [], []
    for recipient in recipients:
        (skipped if normalize_address(recipient.get(key)) in blocked else kept).append(recipient)
    return kept, skipped
