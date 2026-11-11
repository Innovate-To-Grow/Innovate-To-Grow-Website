"""The plain sentences of a review: what each conflict is, why a row has it, and what an action does."""

from __future__ import annotations

from .actions import CREATE, CREATE_CLAIM, UPDATE, Action
from .lookup import EmailRecord, Snapshot

# Conflict slug → (code, title). The review lists the groups in this order of precedence.
CONFLICTS = {
    "privileged_target": ("C2", "A staff or superuser account"),
    "ambiguous_address": ("C3", "The address exists more than once, differing only in letter case"),
    "uuid_email_mismatch": ("C4", "The Member UUID and the Primary Email point to different members"),
    "uuid_not_found": ("C5", "The Member UUID matches nobody"),
    "duplicate_in_sheet": ("C1", "The same person appears more than once in the sheet"),
    "name_differs": ("C6", "Found by email, but the name is different"),
    "address_not_primary": ("C7", "The address is a member's secondary or other email"),
    "unlinked_address": ("C8", "The address exists, but with no member"),
    "exists_but_skip_mode": ("C9", "Matches an existing member, and the upload said to skip those"),
}
PRECEDENCE = list(CONFLICTS)


def conflict_code(conflict: str) -> str:
    return CONFLICTS[conflict][0] if conflict in CONFLICTS else ""


def conflict_title(conflict: str) -> str:
    return CONFLICTS[conflict][1] if conflict in CONFLICTS else ""


def role_of(record: EmailRecord, snapshot: Snapshot) -> str:
    """``the secondary email of Neil Parkhi (member …), whose primary email is x`` (or "a contact email with no member")."""
    owner = snapshot.member(record.member)
    if owner is None:
        return "a contact email with no member"
    role = f"the {record.type} email of {owner.label}"
    if record.type == "primary":
        return role
    primary = owner.primary
    return f"{role}, whose primary email is {primary.address if primary else '(none)'}"


def why(conflict: str, values: dict, snapshot: Snapshot, **facts) -> str:
    """One sentence saying why the row needs a decision."""
    sentence = _WHY.get(conflict)
    if sentence is None:
        return ""
    address = values.get("primary_email") or ""
    context = _Why(
        values, snapshot, address, snapshot.email_records(address), snapshot.member(facts.get("target")), facts
    )
    return sentence(context)


class _Why:
    def __init__(self, values, snapshot, address, records, target, facts):
        self.values, self.snapshot, self.address = values, snapshot, address
        self.records, self.target, self.facts = records, target, facts


def _duplicate(c: _Why) -> str:
    rows = ", ".join(str(number) for number in c.facts.get("group", []))
    who = c.target.label if c.target else c.address
    return f"Rows {rows} all resolve to {who}. Only one of them can be applied."


def _privileged(c: _Why) -> str:
    return (
        f"You do not have permission to update {c.target.label} (only an I2G Master may change staff and superuser "
        "accounts)."
    )


def _ambiguous(c: _Why) -> str:
    holders = "; ".join(f"{record.address} is {role_of(record, c.snapshot)}" for record in c.records)
    return (
        f"{c.address} matches {len(c.records)} contact emails that differ only in letter case ({holders}). Merge the "
        "duplicates under Contact Emails, or choose one here."
    )


def _mismatch(c: _Why) -> str:
    by_uuid = c.snapshot.member(c.facts.get("uuid_member"))
    return f"The Member UUID names {by_uuid.label}, but {c.address} is {role_of(c.records[0], c.snapshot)}."


def _found_elsewhere(c: _Why) -> str:
    return f"{c.address} is {role_of(c.records[0], c.snapshot)}."


def _name_differs(c: _Why) -> str:
    sheet = " ".join(part for part in (c.values.get("first_name"), c.values.get("last_name")) if part)
    return f"{_found_elsewhere(c)} The sheet names {sheet!r}, but the member is {c.target.full_name!r}."


def _unlinked(c: _Why) -> str:
    created = c.records[0].created[:10] if c.records and c.records[0].created else "an unknown date"
    return f"{c.address} is a contact email with no member (added {created})."


def _skip_mode(c: _Why) -> str:
    how = "The Member UUID names" if c.facts.get("matched_by") == "uuid" else f"{c.address} is the primary email of"
    if c.facts.get("no_permission"):
        return f"{how} {c.target.label}, and you do not have permission to change members."
    return f"{how} {c.target.label}, and the upload said to skip rows that match an existing member."


_WHY = {
    "duplicate_in_sheet": _duplicate,
    "privileged_target": _privileged,
    "ambiguous_address": _ambiguous,
    "uuid_email_mismatch": _mismatch,
    "uuid_not_found": lambda c: _uuid_not_found(c.values),
    "name_differs": _name_differs,
    "address_not_primary": _found_elsewhere,
    "unlinked_address": _unlinked,
    "exists_but_skip_mode": _skip_mode,
}


def _uuid_not_found(values: dict) -> str:
    text = values.get("member_uuid_text") or values.get("member_uuid") or ""
    if not values.get("member_uuid"):
        return f"The Member UUID cell {text!r} is not a UUID."
    return (
        f"No member has the Member UUID {text}: it may be a deleted member, a typo, or a sheet exported from another "
        "site (such as staging)."
    )


def describe_action(action: Action | None, snapshot: Snapshot, values: dict) -> str:
    """What an action does, in a few words: "update Neil Parkhi (member …)", "create a new member"."""
    if action is None:
        return "skip it"
    if action.kind == CREATE:
        return f"create a new member with {values.get('primary_email')}"
    if action.kind == CREATE_CLAIM:
        return f"create a new member around the unlinked address {values.get('primary_email')}"
    if action.kind == UPDATE:
        member = snapshot.member(action.target)
        return f"update {member.label if member else 'the member'}"
    return "skip it"
