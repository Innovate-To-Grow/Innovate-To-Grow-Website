"""The bulk-mail suppression list: addresses staff marked undeliverable or suppressed on Email Monitoring → Bounced
addresses (``BouncedAddress.suppressed_at``).

Every campaign audience skips them when it is resolved (``apps.mail.services.audience``), and every campaign send
checks again just before the provider call, so a recipient queued before the address was suppressed is not sent
either. Transactional mail (sign-in and verification codes, password codes, tickets, notifications, inbox replies)
never reads this list: the person may have fixed their mailbox, and those messages must still arrive.

Addresses compare in their bare, lower-case form, so ``Person@Example.com`` and ``Name <person@example.com>`` are one
address.
"""

from apps.core.services.email.telemetry import text
from apps.mail.models import BouncedAddress

SKIPPED_MESSAGE = "Not sent: this address is suppressed for bulk mail (Email Monitoring → Bounced addresses)."


def normalize_address(value) -> str:
    """The bare, lower-case address of ``value``, or "" when it holds none."""
    return text.address(value)


def suppressed_addresses() -> frozenset[str]:
    """Every suppressed address (one query; the list is small)."""
    rows = BouncedAddress.objects.filter(suppressed_at__isnull=False).order_by()
    return frozenset(rows.values_list("address", flat=True))


def is_suppressed(address) -> bool:
    normalized = normalize_address(address)
    return bool(normalized) and BouncedAddress.objects.filter(address=normalized, suppressed_at__isnull=False).exists()


def split_suppressed(recipients, *, key: str = "email") -> tuple[list, list]:
    """``(kept, skipped)``: the audience rows whose address is not suppressed, and those that are."""
    blocked = suppressed_addresses()
    if not blocked:
        return list(recipients), []
    kept, skipped = [], []
    for recipient in recipients:
        (skipped if normalize_address(recipient.get(key)) in blocked else kept).append(recipient)
    return kept, skipped
