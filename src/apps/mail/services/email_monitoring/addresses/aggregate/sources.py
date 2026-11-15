"""Counting one batch of each bounce source into ``BouncedAddress`` rows.

- **Microsoft Graph** (``core.EmailBounce``): a report row is never changed after it is saved, so each one is counted
  once, in creation order, and its count stays when the row is purged. The campaign is the matched email's
  (``exact``) or, for an unmatched report, the one campaign that mailed the address in the matching window before
  it (``likely``; none when several did).
- **Amazon SES** (``RecipientLog`` bounce and complaint events): a log is updated when an event arrives, so each log
  is kept as one ``BouncedAddressCampaign`` row (an upsert, so seeing it again changes nothing) and the address's SES
  counts are recounted from those rows.

Graph reports are counted by coarse classification and by category. Only strong evidence reopens an address that was
dismissed (queue state only): a report that the address does not exist or that its mailbox is disabled, matched to an
email the site sent, or an SES permanent bounce or complaint, arriving after the dismissal. Temporary failures,
rejections by spam filters, relays or policy, delays and unknown failures never reopen anything, and neither does an
unmatched report: anyone can mail the mailbox a report-shaped message.
"""

from django.db.models import Q

from apps.core.models import EmailBounce
from apps.mail.models import BouncedAddress, BouncedAddressAction, BouncedAddressCampaign

Classification = EmailBounce.Classification
Category = EmailBounce.Category
Source = BouncedAddressCampaign.Source
Match = BouncedAddressCampaign.Match
COUNT_FIELDS = {
    Classification.HARD: "hard_count",
    Classification.SOFT: "soft_count",
    Classification.REJECTED: "rejected_count",
    Classification.DELAYED: "delayed_count",
    Classification.UNKNOWN: "unknown_count",
}


def after_cursor(rows, state, field: str):
    """``rows`` past the state's cursor, in (``field``, pk) order."""
    if state.cursor_at is not None:
        rows = rows.filter(
            Q(**{f"{field}__gt": state.cursor_at}) | Q(**{field: state.cursor_at, "pk__gt": state.cursor_id})
        )
    return rows.order_by(field, "pk")


def locked_row(address: str) -> BouncedAddress:
    row, _created = BouncedAddress.objects.get_or_create(address=address)
    return BouncedAddress.objects.select_for_update().get(pk=row.pk)


def _reopen(row: BouncedAddress, why: str, at) -> None:
    """Reopen a dismissed address for a report that arrived after it was dismissed. A rebuild recounting older
    reports reopens nothing, and neither does a report when the dismissal's time is unknown."""
    if row.status != BouncedAddress.Status.DISMISSED or row.reviewed_at is None or at is None or at <= row.reviewed_at:
        return
    row.status = BouncedAddress.Status.OPEN
    row.resolution = ""
    BouncedAddressAction.objects.create(
        bounced_address=row,
        address=row.address,
        action=BouncedAddressAction.Action.REOPEN,
        actor_label="Automatic: queue state only",
        role_before=row.role,
        role_after=row.role,
        note=why[:500],
        member_id=row.member_id,
        member_ref=row.member_id,
    )
