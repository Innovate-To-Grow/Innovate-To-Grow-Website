"""The filtered Bounced addresses list as an ``.xlsx`` workbook (at most ``EMAIL_MONITORING["address_export_max_rows"]``
rows, in the list's order). Every cell goes through ``safe_sheet_value``, so no address, name or diagnostic text is
ever evaluated as a spreadsheet formula. Members and roles are read live, as on the page."""

from collections import defaultdict
from io import BytesIO

from django.conf import settings
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from apps.core.services.helpers.sheets_safety import safe_sheet_value
from apps.mail.models import BouncedAddressCampaign, EmailCampaign

from .matching import AddressMatch, match_addresses, refresh_cached_links

COLUMNS = (
    ("Address", 34),
    ("Status", 12),
    ("Resolution", 18),
    ("Role", 16),
    ("Member", 28),
    ("Member id", 38),
    ("Member active", 14),
    ("Member staff", 13),
    ("Verified", 10),
    ("Subscribed", 11),
    ("Suppression", 22),
    ("Suppressed at", 20),
    ("Hard", 7),
    ("Soft", 7),
    ("Rejected", 9),
    ("Delayed", 9),
    ("Unknown", 9),
    ("Complaints", 11),
    ("First bounce", 20),
    ("Last bounce", 20),
    ("Last status code", 16),
    ("Last reason", 36),
    ("Last diagnostic", 50),
    ("Campaigns", 50),
    ("Suggestion", 40),
    ("Reviewed by", 28),
    ("Reviewed at", 20),
    ("Review note", 40),
)


def _when(value) -> str:
    return timezone.localtime(value).strftime("%Y-%m-%d %H:%M") if value else ""


def _yes(value) -> str:
    if value is None:
        return ""
    return "Yes" if value else "No"


def _campaign_names(rows) -> dict:
    """``{row id: "Campaign A; Campaign B (likely)"}`` for the exported rows."""
    links = list(
        BouncedAddressCampaign.objects.filter(bounced_address__in=rows).values_list(
            "bounced_address_id", "campaign_id", "match"
        )
    )
    names = dict(EmailCampaign.objects.filter(pk__in={link[1] for link in links}).values_list("pk", "name"))
    exact = defaultdict(dict)
    for row_id, campaign_id, match in links:
        exact[row_id][campaign_id] = exact[row_id].get(campaign_id, False) or match == "exact"
    found = {}
    for row_id, campaigns in exact.items():
        labels = [
            (names.get(campaign_id) or "(deleted campaign)") + ("" if is_exact else " (likely)")
            for campaign_id, is_exact in campaigns.items()
        ]
        found[row_id] = "; ".join(sorted(labels))
    return found


def _values(row, match: AddressMatch, campaigns: str) -> list:
    contact, member = match.contact, match.member
    return [
        row.address,
        row.get_status_display(),
        row.resolution,
        row.get_role_display(),
        member.get_full_name() if member else "",
        str(member.pk) if member else "",
        _yes(member.is_active) if member else "",
        _yes(member.is_staff or member.is_superuser) if member else "",
        _yes(contact.verified) if contact else "",
        _yes(contact.subscribe) if contact else "",
        row.get_suppression_display() if row.is_suppressed else "",
        _when(row.suppressed_at),
        row.hard_total,
        row.soft_total,
        row.rejected_count,
        row.delayed_count,
        row.unknown_total,
        row.complaint_count,
        _when(row.first_bounce_at),
        _when(row.last_bounce_at),
        row.last_status_code,
        row.last_reason,
        row.last_diagnostic,
        campaigns,
        row.get_suggestion_display() if row.suggestion else "",
        str(row.reviewed_by) if row.reviewed_by_id else "",
        _when(row.reviewed_at),
        row.review_note,
    ]


def _cell(value):
    """Numbers as numbers; text without the control characters a workbook cannot hold (a member's name may carry
    one), then neutralised so a spreadsheet never evaluates it as a formula."""
    if isinstance(value, int):
        return value
    return safe_sheet_value(ILLEGAL_CHARACTERS_RE.sub("", str(value or "")))


def export_rows(rows) -> bytes:
    rows = list(rows[: int(settings.EMAIL_MONITORING["address_export_max_rows"])])
    matches = match_addresses(row.address for row in rows)
    refresh_cached_links(rows, matches)
    campaigns = _campaign_names(rows)
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("Bounced addresses")
    for index, (_label, width) in enumerate(COLUMNS, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    header = []
    for label, _width in COLUMNS:
        cell = WriteOnlyCell(sheet, value=label)
        cell.font = Font(bold=True)
        header.append(cell)
    sheet.append(header)
    for row in rows:
        values = _values(row, matches.get(row.address) or AddressMatch(row.address), campaigns.get(row.pk, ""))
        sheet.append([_cell(value) for value in values])
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
