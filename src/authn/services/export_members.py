"""
Export members to Excel (.xlsx) using openpyxl in write-only mode for performance.
"""

from io import BytesIO

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


def export_members_to_excel(queryset) -> bytes:
    """
    Export a queryset of Member objects to a styled Excel workbook.

    Uses write-only mode and prefetch_related for efficient handling of large datasets.

    Args:
        queryset: A Django QuerySet of Member objects.

    Returns:
        bytes: The Excel file content.
    """
    queryset = queryset.only(
        "first_name",
        "last_name",
        "middle_name",
        "username",
        "organization",
        "is_active",
        "is_active_member",
        "is_staff",
        "email_subscribe",
        "date_joined",
    ).prefetch_related("contact_emails", "contact_phones", "groups")

    wb = Workbook(write_only=True)
    ws = wb.create_sheet("Members")

    # Column definitions: (header_label, width)
    columns = [
        ("First Name", 15),
        ("Last Name", 15),
        ("Middle Name", 15),
        ("Username", 20),
        ("Primary Email", 30),
        ("Organization", 25),
        ("Active", 10),
        ("Active Member", 14),
        ("Staff", 10),
        ("Email Subscribe", 16),
        ("Date Joined", 18),
        ("Contact Emails", 40),
        ("Contact Phones", 25),
        ("Groups", 30),
    ]

    # Set column widths before appending rows
    for col_idx, (_label, width) in enumerate(columns, 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    # Header styles (matching import template)
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_alignment = Alignment(horizontal="center", vertical="center")

    # Write styled header row
    header_cells = []
    for label, _width in columns:
        cell = WriteOnlyCell(ws, value=label)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment
        header_cells.append(cell)
    ws.append(header_cells)

    # Write data rows — plain values, no per-cell styling for performance
    for member in queryset:
        contact_emails = member.contact_emails.all()
        contact_phones = member.contact_phones.all()
        groups = member.groups.all()

        email_parts = []
        for ce in contact_emails:
            label = ce.email_address
            if ce.verified:
                label += " (verified)"
            email_parts.append(label)

        ws.append(
            [
                member.first_name,
                member.last_name,
                member.middle_name or "",
                member.username,
                member.get_primary_email(),
                member.organization or "",
                "Yes" if member.is_active else "No",
                "Yes" if member.is_active_member else "No",
                "Yes" if member.is_staff else "No",
                "Yes" if member.email_subscribe else "No",
                member.date_joined.strftime("%Y-%m-%d %H:%M") if member.date_joined else "",
                ", ".join(email_parts),
                ", ".join(cp.phone_number for cp in contact_phones),
                ", ".join(g.name for g in groups),
            ]
        )

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output.getvalue()
