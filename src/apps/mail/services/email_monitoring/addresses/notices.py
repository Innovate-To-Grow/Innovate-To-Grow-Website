"""Counting "left the organisation" automatic replies into bounced addresses (the ``inbound`` source).

The helpdesk classifies every Inbox message (``core.InboundMessage``): an automatic reply saying that the person left,
retired or changed address, or that the mailbox is closed, is ``left_org``. When it answers an email the site sent, the
helpdesk keeps the address that email went to (``result["site_recipient"]``) and any address the notice names instead
(``result["named_contact"]``, a hint from its text). Only such matched notices count, and against the address the site
mailed (the notice may come from another address of the same organisation): anyone can mail the mailbox a
notice-shaped message, and one that answers nothing the site sent says nothing about an address it mails. An
out-of-office reply is never counted: the helpdesk classifies a notice that mentions an absence as one.

A notice is evidence, shown with a suggestion: counting never suppresses, unsubscribes or changes anything, and a
notice never reopens a dismissed address (only a report that the address does not exist or that its mailbox is
disabled does). Rows are read in processing order from a cursor, so each notice is counted once, and the counts stay
after the queue rows are purged (``inbound_retention_days``). A rebuild leaves them as they are: a notice is never
classified again, and the queue keeps only its last 90 days.
"""

from collections import defaultdict

from apps.core.models import InboundMessage
from apps.core.services.email.inbound import rules
from apps.mail.models import BouncedAddress
from apps.mail.services.suppression import normalize_address

from . import sources

FIELDS = ("pk", "processed_at", "received_at", "result")
CONTACT_KINDS = frozenset(BouncedAddress.CONTACT_KINDS)


def rows(state, until=None):
    """The matched left-the-organisation notices past the state's cursor, in processing order."""
    notices = InboundMessage.objects.filter(
        status=InboundMessage.Status.DONE,
        classification=rules.LEFT_ORG,
        processed_at__isnull=False,
        result__has_key="site_recipient",
    )
    if until is not None:
        notices = notices.filter(processed_at__lte=until)
    return sources.after_cursor(notices, state, "processed_at")


def _contact(row: BouncedAddress, result: dict) -> tuple[str, str]:
    contact = normalize_address(result.get("named_contact"))
    kind = str(result.get("named_contact_kind") or "")
    if not contact or contact == row.address or len(contact) > 254:
        return "", ""
    return contact, kind if kind in CONTACT_KINDS else ""


def _result(notice: dict) -> dict:
    result = notice["result"]
    return result if isinstance(result, dict) else {}


def _add_notice(row: BouncedAddress, notice: dict) -> None:
    at, result = notice["received_at"], _result(notice)
    row.left_org_count += 1
    if row.left_org_first_at is None or at < row.left_org_first_at:
        row.left_org_first_at = at
    if row.left_org_last_at is None or at >= row.left_org_last_at:
        row.left_org_last_at = at
        row.left_org_contact, row.left_org_contact_kind = _contact(row, result)
        ticket = result.get("ticket")
        row.left_org_ticket = ticket if type(ticket) is int and ticket > 0 else None


def count(batch) -> list[BouncedAddress]:
    """Count a batch of notices (``FIELDS`` dicts, in cursor order); return the rows it changed."""
    grouped = defaultdict(list)
    for notice in batch:
        result = _result(notice)
        address = normalize_address(result.get("site_recipient"))
        if address and len(address) <= 254 and not result.get("duplicate"):
            grouped[address].append(notice)
    touched = []
    # Rows are locked in address order, as every counting batch does.
    for address, notices in sorted(grouped.items()):
        row = sources.locked_row(address)
        for notice in notices:
            _add_notice(row, notice)
        touched.append(row)
    return touched
