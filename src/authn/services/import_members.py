"""
Service for importing members from Excel files.

Expected Excel layout:
    First Name, Last Name, When Started, Last Updated,
    Primary Email, Primary Verified, Primary Subscribed,
    Secondary Email, Secondary Verified, Secondary Subscribed,
    Secondary Expired, Secondary Bounced,
    Phone Number, Phone number subscribed, Phone number verified,
    Organization (optional)
"""

import secrets
import string
from dataclasses import dataclass
from datetime import datetime

from django.db import transaction
from django.utils import timezone

try:
    from openpyxl import load_workbook
except ImportError:
    load_workbook = None

from ..models import ContactEmail, ContactPhone, Member


@dataclass
class ImportResult:
    """Result of a member import operation."""

    success: bool
    created_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    errors: list[str] = None
    details: list[dict] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.details is None:
            self.details = []


def generate_random_password(length: int = 12) -> str:
    """Generate a random password."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


# Column header normalization map
HEADER_MAP = {
    "first name": "first_name",
    "first_name": "first_name",
    "firstname": "first_name",
    "last name": "last_name",
    "last_name": "last_name",
    "lastname": "last_name",
    "when started": "when_started",
    "when_started": "when_started",
    "date joined": "when_started",
    "date_joined": "when_started",
    "last updated": "last_updated",
    "last_updated": "last_updated",
    "primary email": "primary_email",
    "primary_email": "primary_email",
    "email": "primary_email",
    "primary verified": "primary_verified",
    "primary_verified": "primary_verified",
    "primary subscribed": "primary_subscribed",
    "primary_subscribed": "primary_subscribed",
    "secondary email": "secondary_email",
    "secondary_email": "secondary_email",
    "secondary verified": "secondary_verified",
    "secondary_verified": "secondary_verified",
    "secondary subscribed": "secondary_subscribed",
    "secondary_subscribed": "secondary_subscribed",
    "secondary expired": "secondary_expired",
    "secondary_expired": "secondary_expired",
    "secondary bounced": "secondary_bounced",
    "secondary_bounced": "secondary_bounced",
    "phone number": "phone_number",
    "phone_number": "phone_number",
    "phone": "phone_number",
    "phone number subscribed": "phone_subscribed",
    "phone_number_subscribed": "phone_subscribed",
    "phone number verified": "phone_verified",
    "phone_number_verified": "phone_verified",
    "organization": "organization",
    "organization (optional)": "organization",
    "company": "organization",
    "org": "organization",
}


def normalize_header(header: str) -> str:
    """Normalize column header to standard field name."""
    if not header:
        return ""
    header = str(header).strip().lower()
    return HEADER_MAP.get(header, header)


def parse_boolean(value) -> bool:
    """Parse various boolean representations."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    str_val = str(value).strip().lower()
    return str_val in ("true", "yes", "1", "y", "active")


def parse_date(value):
    """Parse date value from Excel cell. Returns timezone-aware datetime or None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if timezone.is_naive(value):
            return timezone.make_aware(value)
        return value
    str_val = str(value).strip()
    if not str_val:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M:%S"):
        try:
            dt = datetime.strptime(str_val, fmt)
            return timezone.make_aware(dt)
        except ValueError:
            continue
    return None


def _generate_unique_username(email: str) -> str:
    """Generate a unique username from email address."""
    base = email.split("@")[0].lower()
    base = "".join(c for c in base if c.isalnum() or c in "._-")
    if not base:
        base = "user"

    username = base
    counter = 2
    while Member.all_objects.filter(username=username).exists():
        username = f"{base}_{counter}"
        counter += 1
    return username


def import_members_from_excel(
    file,
    default_password: str | None = None,
    update_existing: bool = False,
) -> ImportResult:
    """
    Import members from an Excel file.

    Expected columns:
        First Name, Last Name, When Started, Last Updated,
        Primary Email, Primary Verified, Primary Subscribed,
        Secondary Email, Secondary Verified, Secondary Subscribed,
        Secondary Expired, Secondary Bounced,
        Phone Number, Phone number subscribed, Phone number verified,
        Organization (optional)

    Args:
        file: Uploaded Excel file
        default_password: Password to set for new users (generates random if None)
        update_existing: Whether to update existing users (matched by primary email)

    Returns:
        ImportResult with counts and any errors
    """
    if load_workbook is None:
        return ImportResult(success=False, errors=["openpyxl library not installed. Please run: pip install openpyxl"])

    result = ImportResult(success=True)

    try:
        wb = load_workbook(filename=file, read_only=True, data_only=True)
        ws = wb.active

        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return ImportResult(success=False, errors=["Excel file is empty"])

        headers = [normalize_header(h) for h in rows[0]]

        if "primary_email" not in headers:
            return ImportResult(
                success=False,
                errors=["Excel file must contain a 'Primary Email' column"],
            )

        for row_num, row in enumerate(rows[1:], start=2):
            if not any(row):
                continue

            row_data = dict(zip(headers, row, strict=False))

            # Use nested atomic() as savepoint so a single row failure
            # does not abort the entire import (needed for PostgreSQL).
            try:
                with transaction.atomic():
                    row_result = _process_member_row(row_num, row_data, default_password, update_existing)
            except Exception as e:
                row_result = {
                    "row": row_num,
                    "status": "skipped",
                    "email": str(row_data.get("primary_email", "")),
                    "error": str(e),
                }

            if row_result["status"] == "created":
                result.created_count += 1
            elif row_result["status"] == "updated":
                result.updated_count += 1
            elif row_result["status"] == "skipped":
                result.skipped_count += 1

            if row_result.get("error"):
                result.errors.append(f"Row {row_num}: {row_result['error']}")

            result.details.append(row_result)

        wb.close()

    except Exception as e:
        result.success = False
        result.errors.append(f"Error processing file: {str(e)}")

    return result


def _process_member_row(
    row_num: int,
    row_data: dict,
    default_password: str | None,
    update_existing: bool,
) -> dict:
    """Process a single row and create/update member with contact info."""
    result = {
        "row": row_num,
        "status": "skipped",
        "email": None,
        "error": None,
    }

    # Extract primary email (required)
    primary_email = str(row_data.get("primary_email", "")).strip() if row_data.get("primary_email") else None
    if not primary_email:
        result["error"] = "Missing primary email"
        return result

    result["email"] = primary_email

    # Extract member fields
    first_name = str(row_data.get("first_name", "")).strip() if row_data.get("first_name") else ""
    last_name = str(row_data.get("last_name", "")).strip() if row_data.get("last_name") else ""
    organization = str(row_data.get("organization", "")).strip() if row_data.get("organization") else ""
    date_joined = parse_date(row_data.get("when_started"))

    # Primary email contact info
    primary_verified = parse_boolean(row_data.get("primary_verified"))
    primary_subscribed = parse_boolean(row_data.get("primary_subscribed"))

    # Secondary email
    secondary_email = str(row_data.get("secondary_email", "")).strip() if row_data.get("secondary_email") else None
    secondary_verified = parse_boolean(row_data.get("secondary_verified"))
    secondary_subscribed = parse_boolean(row_data.get("secondary_subscribed"))

    # Phone
    phone_number = str(row_data.get("phone_number", "")).strip() if row_data.get("phone_number") else None
    # Normalize phone: convert int/float from Excel to string
    if phone_number and phone_number.replace(".", "").replace("-", "").replace("+", "").isdigit():
        phone_number = phone_number.split(".")[0]  # strip trailing .0 from Excel numeric
    phone_subscribed = parse_boolean(row_data.get("phone_subscribed"))
    phone_verified = parse_boolean(row_data.get("phone_verified"))

    # Check if member exists by email
    existing_member = Member.objects.filter(email=primary_email).first()

    if existing_member:
        if update_existing:
            _update_existing_member(
                existing_member,
                first_name=first_name,
                last_name=last_name,
                organization=organization,
                primary_verified=primary_verified,
                primary_subscribed=primary_subscribed,
                secondary_email=secondary_email,
                secondary_verified=secondary_verified,
                secondary_subscribed=secondary_subscribed,
                phone_number=phone_number,
                phone_subscribed=phone_subscribed,
                phone_verified=phone_verified,
            )
            result["status"] = "updated"
        else:
            result["status"] = "skipped"
            result["error"] = f"Member with email {primary_email} already exists"
    else:
        # Create new member
        password = default_password or generate_random_password()
        username = _generate_unique_username(primary_email)

        member = Member.objects.create_user(
            username=username,
            email=primary_email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            organization=organization,
            email_subscribe=primary_subscribed,
            is_active=True,
            is_active_member=True,
        )

        # Set date_joined if provided
        if date_joined:
            Member.objects.filter(pk=member.pk).update(date_joined=date_joined)

        # Create primary ContactEmail
        ContactEmail.objects.create(
            member=member,
            email_address=primary_email,
            email_type="primary",
            verified=primary_verified,
            subscribe=primary_subscribed,
        )

        # Create secondary ContactEmail if provided
        if secondary_email:
            ContactEmail.objects.create(
                member=member,
                email_address=secondary_email,
                email_type="secondary",
                verified=secondary_verified,
                subscribe=secondary_subscribed,
            )

        # Create ContactPhone if provided
        if phone_number:
            ContactPhone.objects.create(
                member=member,
                phone_number=phone_number,
                region="US",
                subscribe=phone_subscribed,
                verified=phone_verified,
            )

        result["status"] = "created"

    return result


def _update_existing_member(
    member,
    *,
    first_name,
    last_name,
    organization,
    primary_verified,
    primary_subscribed,
    secondary_email,
    secondary_verified,
    secondary_subscribed,
    phone_number,
    phone_subscribed,
    phone_verified,
):
    """Update an existing member and their contact info."""
    if first_name:
        member.first_name = first_name
    if last_name:
        member.last_name = last_name
    if organization:
        member.organization = organization
    member.email_subscribe = primary_subscribed
    member.save()

    # Update or create primary ContactEmail
    ContactEmail.objects.update_or_create(
        member=member,
        email_address=member.email,
        defaults={
            "email_type": "primary",
            "verified": primary_verified,
            "subscribe": primary_subscribed,
        },
    )

    # Handle secondary email
    if secondary_email:
        # Remove old secondary emails that don't match
        member.contact_emails.filter(email_type="secondary").exclude(email_address=secondary_email).delete()
        ContactEmail.objects.update_or_create(
            member=member,
            email_address=secondary_email,
            defaults={
                "email_type": "secondary",
                "verified": secondary_verified,
                "subscribe": secondary_subscribed,
            },
        )
    else:
        member.contact_emails.filter(email_type="secondary").delete()

    # Handle phone
    if phone_number:
        existing_phone = member.contact_phones.first()
        if existing_phone:
            existing_phone.phone_number = phone_number
            existing_phone.subscribe = phone_subscribed
            existing_phone.verified = phone_verified
            existing_phone.save()
        else:
            ContactPhone.objects.create(
                member=member,
                phone_number=phone_number,
                region="US",
                subscribe=phone_subscribed,
                verified=phone_verified,
            )
    else:
        member.contact_phones.all().delete()


def generate_template_excel() -> bytes:
    """Generate a template Excel file for member import."""
    if load_workbook is None:
        raise ImportError("openpyxl library not installed")

    from io import BytesIO

    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    wb = Workbook()
    ws = wb.active
    ws.title = "Members"

    headers = [
        ("first_name", "First Name", 15),
        ("last_name", "Last Name", 15),
        ("when_started", "When Started", 15),
        ("last_updated", "Last Updated", 15),
        ("primary_email", "Primary Email", 30),
        ("primary_verified", "Primary Verified", 16),
        ("primary_subscribed", "Primary Subscribed", 18),
        ("secondary_email", "Secondary Email", 30),
        ("secondary_verified", "Secondary Verified", 18),
        ("secondary_subscribed", "Secondary Subscribed", 20),
        ("secondary_expired", "Secondary Expired", 18),
        ("secondary_bounced", "Secondary Bounced", 18),
        ("phone_number", "Phone Number", 18),
        ("phone_subscribed", "Phone number subscribed", 22),
        ("phone_verified", "Phone number verified", 22),
        ("organization", "Organization (optional)", 25),
    ]

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_alignment = Alignment(horizontal="center", vertical="center")
    thin_border = Border(
        left=Side(style="thin"), right=Side(style="thin"), top=Side(style="thin"), bottom=Side(style="thin")
    )

    for col, (_field, label, width) in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=label)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment
        cell.border = thin_border
        ws.column_dimensions[cell.column_letter].width = width

    example_data = [
        "John",
        "Doe",
        "2024-01-15",
        "2024-06-01",
        "john.doe@example.com",
        "TRUE",
        "TRUE",
        "john.d@gmail.com",
        "FALSE",
        "FALSE",
        "FALSE",
        "FALSE",
        "+12095551234",
        "TRUE",
        "FALSE",
        "UC Merced",
    ]

    for col, value in enumerate(example_data, 1):
        cell = ws.cell(row=2, column=col, value=value)
        cell.border = thin_border

    ws_help = wb.create_sheet(title="Instructions")
    instructions = [
        ("Field Descriptions", ""),
        ("", ""),
        ("First Name", "Member's first name"),
        ("Last Name", "Member's last name"),
        ("When Started", "Date the member joined (YYYY-MM-DD or MM/DD/YYYY)"),
        ("Last Updated", "Last update date (informational only, not imported)"),
        ("Primary Email", "Primary email address (REQUIRED - used as login email)"),
        ("Primary Verified", "Whether the primary email is verified (TRUE/FALSE)"),
        ("Primary Subscribed", "Whether the primary email is subscribed (TRUE/FALSE)"),
        ("Secondary Email", "Secondary/alternate email address (optional)"),
        ("Secondary Verified", "Whether the secondary email is verified (TRUE/FALSE)"),
        ("Secondary Subscribed", "Whether the secondary email is subscribed (TRUE/FALSE)"),
        ("Secondary Expired", "Whether the secondary email has expired (informational only)"),
        ("Secondary Bounced", "Whether the secondary email has bounced (informational only)"),
        ("Phone Number", "Phone number in E.164 format, e.g. +12095551234 (optional)"),
        ("Phone number subscribed", "Whether the phone is subscribed (TRUE/FALSE)"),
        ("Phone number verified", "Whether the phone is verified (TRUE/FALSE)"),
        ("Organization (optional)", "Organization or company name"),
        ("", ""),
        ("Notes", ""),
        ("", "Username is auto-generated from the primary email address"),
        ("", "A random password is generated unless a default is specified"),
        ("", "Existing members (matched by primary email) can be updated if the option is enabled"),
        ("", "'Last Updated', 'Secondary Expired', and 'Secondary Bounced' are informational and not stored"),
    ]

    for row, (col1, col2) in enumerate(instructions, 1):
        ws_help.cell(row=row, column=1, value=col1)
        ws_help.cell(row=row, column=2, value=col2)

    ws_help.column_dimensions["A"].width = 25
    ws_help.column_dimensions["B"].width = 60

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return output.getvalue()
