"""Which member a row means, and what a review suggests doing with it."""

from __future__ import annotations

from dataclasses import dataclass

from apps.authn.models import Member

from ...contacts import valid_new_address
from ..lookup.records import Snapshot, us_phone
from ..plan.actions import CREATE, CREATE_CLAIM, UPDATE, Action
from .choices import names_match

READY_CREATE, READY_UPDATE, NO_CHANGE = "ready_create", "ready_update", "no_change"
NEEDS_DECISION, INVALID = "needs_decision", "invalid"
UPDATE_EXISTING, SKIP_EXISTING = "update_existing", "skip_existing"
_PROFILE_LIMITS = {
    "first_name": "First Name",
    "middle_name": "Middle Name",
    "last_name": "Last Name",
    "title": "Title",
    "organization": "Organization",
}


@dataclass
class Context:
    """Who the analysis is for: the upload's mode, whether the actor may change members, and the actor.

    ``actor`` is the Admin the analysis is for (the uploader at upload, the Admin applying at the apply), so the
    lockout rules can refuse a deactivation of their own Admin account; ``None`` for a script.
    """

    mode: str = UPDATE_EXISTING
    can_update: bool = True
    actor: object = None


@dataclass
class Resolution:
    """How one row resolves on its own, before rows are compared with each other."""

    status: str
    conflict: str = ""
    target: str | None = None
    matched_by: str = ""
    record: str | None = None
    invalid: str = ""
    uuid_member: str | None = None
    email_member: str | None = None


def resolve_row(values: dict, snapshot: Snapshot, ctx: Context, *, use_uuid: bool = True) -> Resolution:
    """Resolve one row: Member UUID → Primary Email (any role) → contact with no member → new member."""
    if not values.get("primary_email"):
        return Resolution(INVALID, invalid="Missing primary email")
    too_long = _too_long(values)
    if too_long:
        return Resolution(INVALID, invalid=too_long)
    uuid_member = None
    if use_uuid and (values.get("member_uuid") or values.get("member_uuid_text")):
        uuid_member = snapshot.member(snapshot.uuids.get(values.get("member_uuid") or ""))
        if uuid_member is None:
            return Resolution(NEEDS_DECISION, "uuid_not_found")
    records = snapshot.email_records(values["primary_email"])
    if len(records) > 1:
        return Resolution(NEEDS_DECISION, "ambiguous_address")
    record = records[0] if records else None
    owner = snapshot.member(record.member) if record and record.member else None
    if uuid_member and owner and owner.id != uuid_member.id:
        return Resolution(NEEDS_DECISION, "uuid_email_mismatch", uuid_member=uuid_member.id, email_member=owner.id)
    if record is not None and record.member is None:
        # A contact email with no member, whatever the Member UUID says: the address is not the UUID member's.
        return Resolution(
            NEEDS_DECISION, "unlinked_address", record=record.id, uuid_member=uuid_member.id if uuid_member else None
        )
    target = uuid_member or owner
    if target is None:
        return _resolve_new(values, record)
    owned = record.id if record and record.member == target.id else None
    base = {"target": target.id, "matched_by": "uuid" if uuid_member else record.type, "record": owned}
    if uuid_member:
        base["uuid_member"] = uuid_member.id
    return _resolve_existing(values, snapshot, ctx, base, record, by_uuid=uuid_member is not None)


def _too_long(values: dict) -> str:
    """Why a profile cell can't be stored (longer than its column), or ``""``."""
    for name, label in _PROFILE_LIMITS.items():
        limit = Member._meta.get_field(name).max_length
        if len(values.get(name) or "") > limit:
            return f"{label} is longer than {limit} characters"
    return ""


def _resolve_new(values: dict, record) -> Resolution:
    if not valid_new_address(values["primary_email"]):
        return Resolution(INVALID, invalid=f"Primary Email {values['primary_email']!r} is not a valid email address")
    for name, label in (("first_name", "first name"), ("last_name", "last name")):
        if not values.get(name):
            return Resolution(INVALID, invalid=f"Missing {label}")
    return Resolution(READY_CREATE)


def _resolve_existing(values, snapshot: Snapshot, ctx: Context, base: dict, record, *, by_uuid: bool) -> Resolution:
    target = snapshot.member(base["target"])
    if not by_uuid and not names_match(values, target):
        return Resolution(NEEDS_DECISION, "name_differs", **base)
    if base["record"] and record.type != "primary":
        return Resolution(NEEDS_DECISION, "address_not_primary", **base)
    if ctx.mode == SKIP_EXISTING or not ctx.can_update:
        # Without the change permission a matching row can only be skipped, whatever the upload's mode.
        return Resolution(NEEDS_DECISION, "exists_but_skip_mode", **base)
    return Resolution(READY_UPDATE, **base)


def suggested_action(resolution: Resolution, values: dict, ctx: Context) -> tuple[Action | None, str]:
    """The action the import plan suggests for a row on its own, or None with the reason it would be skipped."""
    if resolution.status == READY_CREATE:
        return Action(CREATE), ""
    if resolution.status == READY_UPDATE:
        return Action(UPDATE, target=resolution.target), ""
    if resolution.conflict == "address_not_primary":
        if ctx.mode == SKIP_EXISTING or not ctx.can_update:
            return None, "The upload said to skip rows that match an existing member"
        return Action(UPDATE, target=resolution.target), ""
    if resolution.conflict == "unlinked_address":
        if resolution.uuid_member:
            return None, "The row's Member UUID names an existing member"
        if values.get("first_name") and values.get("last_name"):
            return Action(CREATE_CLAIM, claim=resolution.record), ""
        return None, "A new member needs a first and a last name"
    skipped = "The upload said to skip rows that match an existing member"
    if resolution.conflict == "exists_but_skip_mode" and ctx.mode == UPDATE_EXISTING:
        skipped = "You do not have permission to change members"
    reasons = {
        "name_differs": "The sheet's name differs from the member's; decide on this row alone",
        "exists_but_skip_mode": skipped,
    }
    return None, reasons.get(resolution.conflict, "This row needs its own decision")


def _attach_candidates(values: dict, snapshot: Snapshot, resolution: Resolution) -> list[str]:
    """Members the row's other cells found (Member UUID, Secondary Email, Phone Number), for "attach to"."""
    found = [resolution.uuid_member] if resolution.uuid_member else []
    for record in snapshot.email_records(values.get("secondary_email")):
        found.append(record.member)
    parsed = us_phone(values.get("phone_number"))
    phone = snapshot.phones.get(parsed[0]) if parsed else None
    if phone is not None:
        found.append(phone.member)
    return [member for member in dict.fromkeys(found) if member and snapshot.member(member)]
