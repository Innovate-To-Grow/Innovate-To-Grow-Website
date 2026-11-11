"""Update existing members from an import.

A row updates the member whose *primary* email is in its Primary Email cell. It overwrites the profile fields it
fills in, applies the Primary Verified/Subscribed cells in the safe direction only, and adds the secondary email
and phone number it names (``contacts.py``). It never deletes, re-subscribes, un-verifies, or changes whether a
member is active. Every row that is skipped, and every cell that is not applied, is reported with the reason.
"""

from __future__ import annotations

from collections.abc import Callable

from django.db import transaction

from .contacts import apply_primary_flags, sync_phone, sync_secondary_email
from .matching import lookup_contact_emails, member_label, update_skip_reason
from .types import ImportResult

# Model defaults, used when a brand-new contact row is created and the sheet supplies no flag.
_EMAIL_DEFAULTS = {"verified": False, "subscribe": True}
_PHONE_DEFAULTS = {"verified": False, "subscribe": False}

STAFF_COLUMN_IGNORED = "Staff column ignored (only an I2G Master may change staff status)"
ACTIVE_COLUMN_IGNORED = (
    "Active column ignored: the member stays {state} (an import never activates or deactivates an existing member; "
    "use the Activate/Deactivate actions on the member list)"
)
_PROFILE_FIELDS = ("first_name", "last_name", "middle_name", "title", "organization")


def _flag(parsed_value, current, default):
    """Apply the sheet's flag, or keep what is stored when the sheet does not supply one."""
    if parsed_value is not None:
        return parsed_value
    return default if current is None else current


def bulk_update_members(
    rows: list[dict],
    result: ImportResult,
    update_member_allowed: Callable[[object], bool] | None = None,
    allow_privilege_fields: bool = False,
) -> None:
    """Update the member each row names by primary email; skip every other row and say why."""
    matches_by_address = lookup_contact_emails(row["primary_email"] for row in rows)
    for parsed in rows:
        matches = matches_by_address.get(parsed["primary_email"].lower(), [])
        if len(matches) != 1 or matches[0].member is None or matches[0].email_type != "primary":
            reason, member = update_skip_reason(parsed["primary_email"], matches)
            result.skip_row(parsed["row"], reason, member)
            continue
        member = matches[0].member
        if update_member_allowed is not None and not update_member_allowed(member):
            result.skip_row(
                parsed["row"],
                f"You do not have permission to update {member_label(member)} (only an I2G Master may change staff "
                "and superuser accounts)",
                member,
            )
            continue
        _update_row(member, parsed, result, allow_privilege_fields)


def _update_row(member, parsed: dict, result: ImportResult, allow_privilege_fields: bool) -> None:
    # Taken before the row is applied: a failed row leaves the sheet's values on the in-memory instance.
    label = member_label(member)
    try:
        # One savepoint per row: a failing row is rolled back on its own and the import goes on.
        with transaction.atomic():
            notes = update_single_member(member, parsed, allow_privilege_fields=allow_privilege_fields)
    except Exception as exc:  # noqa: BLE001
        result.skip_row(parsed["row"], f"could not update {label}: {exc}. Nothing in this row was changed", member)
        return
    result.updated_count += 1
    for note in [*parsed.get("notes", []), *notes]:
        result.note_row(parsed["row"], note, member)


def update_single_member(member, parsed: dict, allow_privilege_fields: bool = False) -> list[str]:
    """Apply one row to ``member`` and return what it asked for that was not applied, or was kept.

    The Primary Verified/Subscribed cells touch only the address in the Primary Email cell, and only when this
    member owns it. The primary email itself is never created, re-typed or deleted here.
    """
    notes: list[str] = []
    _apply_profile_fields(member, parsed, allow_privilege_fields, notes)
    primary = member.contact_emails.filter(email_address__iexact=parsed["primary_email"]).first()
    if primary is not None:
        apply_primary_flags(primary, parsed, notes)
    sync_secondary_email(member, parsed, notes)
    sync_phone(member, parsed, notes)
    return notes


def _apply_profile_fields(member, parsed: dict, allow_privilege_fields: bool, notes: list[str]) -> None:
    """Overwrite the profile fields the row fills in; blank cells keep the current value.

    Only the fields the row changes are written. ``member`` was loaded before the rows were applied, so a full save
    could put back a value an admin changed meanwhile, such as reactivating a member deactivated mid-import.
    """
    changed = [name for name in _PROFILE_FIELDS if parsed[name] and parsed[name] != getattr(member, name)]
    for name in changed:
        setattr(member, name, parsed[name])
    # Reactivating would undo an admin's deactivation, and activating ends an unfinished sign-up
    # (``Member.save`` clears ``registration_pending``); deactivating locks the member out. None of that
    # happens from a sheet, which may be an old export.
    if parsed["is_active"] is not None and parsed["is_active"] != member.is_active:
        notes.append(ACTIVE_COLUMN_IGNORED.format(state="active" if member.is_active else "inactive"))
    # ``is_staff`` is an I2G Master responsibility (see MemberAdmin.superuser_only_fields). The
    # export writes a Staff column, so without this gate the export -> edit -> re-import round trip
    # was a way for any authn-app admin to mint staff accounts or lock the superuser out.
    if parsed["is_staff"] is not None and parsed["is_staff"] != member.is_staff:
        if allow_privilege_fields:
            member.is_staff = parsed["is_staff"]
            changed.append("is_staff")
        else:
            notes.append(STAFF_COLUMN_IGNORED)
    if changed:
        member.save(update_fields=[*changed, "updated_at"])
