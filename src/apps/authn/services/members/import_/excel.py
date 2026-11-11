"""Excel import implementation for members."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.utils import timezone

try:
    from openpyxl import load_workbook
except ImportError:  # pragma: no cover - guarded at runtime
    load_workbook = None

from apps.authn.models import ContactEmail, ContactPhone, Member

from .contacts import phone_parts, valid_new_address
from .matching import (
    create_only_skip_reason,
    email_holder,
    lookup_contact_emails,
    lookup_contact_phones,
    phone_holder,
)
from .operations import _EMAIL_DEFAULTS, _PHONE_DEFAULTS, _flag, bulk_update_members
from .parsing import generate_random_password, normalize_header, parse_row
from .types import ImportResult

BATCH_SIZE = 500


@dataclass
class _CreationPlan:
    """Records to bulk-create for rows that are new members, and the rows that update existing ones."""

    members: list = field(default_factory=list)
    emails: list = field(default_factory=list)
    phones: list = field(default_factory=list)
    rows_to_update: list = field(default_factory=list)
    # (row, note) for the created rows; reported only once the creation has committed.
    notes: list = field(default_factory=list)


@dataclass
class _Claims:
    """Addresses (lower-cased) and phone numbers already taken, each with who holds it, for the report."""

    emails: dict[str, str] = field(default_factory=dict)
    phones: dict[str, str] = field(default_factory=dict)


def _parse_unique_rows(raw_rows, headers, result: ImportResult) -> list[dict]:
    """Parse data rows, skipping blank ones and reporting rows without (or repeating) a primary email."""
    parsed_rows = []
    first_row_with: dict[str, int] = {}
    for row_num, row in enumerate(raw_rows[1:], start=2):
        if not any(row):
            continue
        parsed = parse_row(row_num, dict(zip(headers, row, strict=False)))
        if not parsed["primary_email"]:
            result.skip_row(row_num, "Missing primary email")
            continue
        email_key = parsed["primary_email"].lower()
        if email_key in first_row_with:
            result.skip_row(
                row_num,
                f"Duplicate email in file ({parsed['primary_email']}): row {first_row_with[email_key]} has it too, "
                "and only that row is imported",
            )
            continue
        first_row_with[email_key] = row_num
        parsed_rows.append(parsed)
    return parsed_rows


def _new_member(parsed: dict, hashed_pw: str, now) -> Member:
    return Member(
        password=hashed_pw,
        first_name=parsed["first_name"],
        last_name=parsed["last_name"],
        middle_name=parsed["middle_name"] or None,
        title=parsed["title"] or None,
        organization=parsed["organization"],
        is_active=parsed["is_active"] if parsed["is_active"] is not None else True,
        date_joined=parsed["date_joined"] or now,
    )


def _creation_problem(parsed: dict, claims: _Claims) -> str | None:
    """Why the row can't create a new member, or None."""
    address = parsed["primary_email"]
    if not valid_new_address(address):
        return f"Primary Email {address!r} is not a valid email address"
    if not parsed["first_name"]:
        return "Missing first name"
    if not parsed["last_name"]:
        return "Missing last name"
    # The exists-check routed every address already stored to the update path, so a claim here is an earlier
    # row's Secondary Email. Creating the member anyway would leave it with no ContactEmail, unable to sign in.
    holder = claims.emails.get(address.lower())
    if holder:
        return f"{address} is already used by {holder}"
    return None


def _plan_creations(parsed_rows, result: ImportResult, *, update_existing: bool, default_password) -> _CreationPlan:
    existing = lookup_contact_emails(
        [*(parsed["primary_email"] for parsed in parsed_rows), *(parsed["secondary_email"] for parsed in parsed_rows)]
    )
    existing_phones = lookup_contact_phones(phone_parts(parsed["phone_number"])[0] for parsed in parsed_rows)
    claims = _Claims(
        emails={key: email_holder(contacts) for key, contacts in existing.items()},
        phones={number: phone_holder(phone) for number, phone in existing_phones.items()},
    )
    hashed_pw = make_password(default_password or generate_random_password())
    plan = _CreationPlan()
    now = timezone.now()

    for parsed in parsed_rows:
        matches = existing.get(parsed["primary_email"].lower())
        if matches:
            if update_existing:
                plan.rows_to_update.append(parsed)
            else:
                reason, member = create_only_skip_reason(parsed["primary_email"], matches)
                result.skip_row(parsed["row"], reason, member)
            continue
        problem = _creation_problem(parsed, claims)
        if problem:
            result.skip_row(parsed["row"], problem)
            continue

        member = _new_member(parsed, hashed_pw, now)
        notes = list(parsed["notes"])
        _append_contact_records(member, parsed, plan, claims, notes)
        plan.members.append(member)
        plan.notes.extend((parsed["row"], note) for note in notes)
        result.created_count += 1
    return plan


def _bulk_create(plan: _CreationPlan) -> None:
    with transaction.atomic():
        # bulk_create bypasses post_save signals, so the Google-Sheet sync
        # signal handlers in authn/signals.py will not fire here. Admins
        # should run the "Sync ALL members to Google Sheet" admin action
        # after import if auto-sync is enabled.
        if plan.members:
            Member.objects.bulk_create(plan.members, batch_size=BATCH_SIZE)
        if plan.emails:
            ContactEmail.objects.bulk_create(plan.emails, batch_size=BATCH_SIZE)
        if plan.phones:
            ContactPhone.objects.bulk_create(plan.phones, batch_size=BATCH_SIZE)


def import_members_from_excel(
    file,
    default_password: str | None = None,
    update_existing: bool = False,
    update_member_allowed: Callable[[Member], bool] | None = None,
    allow_privilege_fields: bool = False,
) -> ImportResult:
    """Import members from an Excel file using bulk inserts when possible.

    New members are created from their rows. With ``update_existing``, a row whose Primary Email is an existing
    member's primary email updates that member without deleting anything (see ``operations.py``). Every row that is
    not imported, and every cell that is not applied, is reported with the reason.
    """
    if load_workbook is None:
        return ImportResult(success=False, errors=["openpyxl library not installed. Please run: pip install openpyxl"])

    result = ImportResult(success=True)
    try:
        workbook = load_workbook(filename=file, read_only=True, data_only=True)
        worksheet = workbook.active
        raw_rows = list(worksheet.iter_rows(values_only=True))
        workbook.close()
        if not raw_rows:
            return ImportResult(success=False, errors=["Excel file is empty"])

        headers = [normalize_header(header) for header in raw_rows[0]]
        if "primary_email" not in headers:
            return ImportResult(success=False, errors=["Excel file must contain a 'Primary Email' column"])

        parsed_rows = _parse_unique_rows(raw_rows, headers, result)
        if not parsed_rows:
            return result
        plan = _plan_creations(parsed_rows, result, update_existing=update_existing, default_password=default_password)
        _bulk_create(plan)
    except Exception as exc:  # noqa: BLE001
        result.success = False
        result.created_count = 0
        result.errors.append(f"Error creating members: {exc}")
        return result

    for row, note in plan.notes:
        result.note_row(row, note)
    if plan.rows_to_update:
        bulk_update_members(
            plan.rows_to_update,
            result,
            update_member_allowed,
            allow_privilege_fields=allow_privilege_fields,
        )
    result.sort_by_row()
    return result


def _append_contact_records(member, parsed: dict, plan: _CreationPlan, claims: _Claims, notes: list[str]) -> None:
    """Queue a new member's contact records. The sheet's flags are trusted for a brand-new member's own contacts."""
    plan.emails.append(
        ContactEmail(
            member=member,
            email_address=parsed["primary_email"],
            email_type="primary",
            verified=_flag(parsed["primary_verified"], None, _EMAIL_DEFAULTS["verified"]),
            subscribe=_flag(parsed["primary_subscribed"], None, _EMAIL_DEFAULTS["subscribe"]),
        )
    )
    claims.emails[parsed["primary_email"].lower()] = f"row {parsed['row']} of this file"
    _append_secondary(member, parsed, plan, claims, notes)
    _append_phone(member, parsed, plan, claims, notes)


def _append_secondary(member, parsed: dict, plan: _CreationPlan, claims: _Claims, notes: list[str]) -> None:
    address = parsed["secondary_email"]
    if not address:
        return
    key = address.lower()
    if key == parsed["primary_email"].lower():
        notes.append("Secondary Email is the same as the Primary Email; ignored")
    elif key in claims.emails:
        notes.append(f"Secondary Email {address} is already used by {claims.emails[key]}; not added")
    elif not valid_new_address(address):
        notes.append(f"Secondary Email {address!r} is not a valid email address; ignored")
    else:
        plan.emails.append(
            ContactEmail(
                member=member,
                email_address=address,
                email_type="secondary",
                verified=_flag(parsed["secondary_verified"], None, _EMAIL_DEFAULTS["verified"]),
                subscribe=_flag(parsed["secondary_subscribed"], None, _EMAIL_DEFAULTS["subscribe"]),
            )
        )
        claims.emails[key] = f"row {parsed['row']} of this file"


def _append_phone(member, parsed: dict, plan: _CreationPlan, claims: _Claims, notes: list[str]) -> None:
    if not parsed["phone_number"]:
        return
    national, region = phone_parts(parsed["phone_number"])
    if not national:
        notes.append(f"Phone Number {parsed['phone_number']} has no digits after the country code; ignored")
    elif national in claims.phones:
        e164 = ContactPhone(phone_number=national, region=region).to_e164()
        notes.append(f"Phone Number {e164} is already used by {claims.phones[national]}; not added")
    else:
        plan.phones.append(
            ContactPhone(
                member=member,
                phone_number=national,
                region=region,
                subscribe=_flag(parsed["phone_subscribed"], None, _PHONE_DEFAULTS["subscribe"]),
                verified=_flag(parsed["phone_verified"], None, _PHONE_DEFAULTS["verified"]),
            )
        )
        claims.phones[national] = f"row {parsed['row']} of this file"
