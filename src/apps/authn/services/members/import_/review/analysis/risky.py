"""Risky changes: what a row may do to the member it updates only when the admin ticks it (R1–R7, R9).

Each item is its own tick, off by default, so every deletion, re-subscription, un-verification and verification is a
separate decision. Verifying (R9) is one too: a verified address is a working sign-in factor (an email code), so a
sheet never creates one without a tick. R6 and R9 cover email addresses only. A phone number's verified status never
changes in an import, with or without a tick: the Phone Verified column is ignored, and only the member's own one-time
code verifies a number. Admin access never changes in an import either (R8 is retired): the Admin (or Staff) column is
ignored. An item that may not be ticked stays visible with the reason: the address the row was matched on, the
member's only verified sign-in contact (the rule of ``services/account/recovery.py``), a self-service sign-up the
person has not finished (only they can finish it, by confirming their email), or a deactivation the Admin lockout
rules refuse (your own Admin account, or the last active Admin; ``services/members/admins``). The planner re-checks the
ticks together against the last-sign-in-contact rule, and the apply checks every ticked deactivation together.
"""

from __future__ import annotations

from ....admins import DEACTIVATE, admin_removal_refusal
from ..lookup.records import MemberRecord, Snapshot, address_key, us_phone

RISKY_TYPES = {
    "R1": "Remove secondary emails: the Secondary Email cell is blank",
    "R2": "Remove the member's other secondary emails",
    "R3": "Remove phone numbers: the Phone Number cell is blank",
    "R4": "Remove the old phone numbers the sheet's number replaces",
    "R5": "Re-subscribe (only with the person's consent)",
    "R6": "Mark email addresses unverified",
    "R7": "Deactivate or reactivate members",
    "R9": "Mark email addresses verified (each becomes a sign-in factor)",
}
MATCHED = "This is the address the row was matched on"
PENDING = (
    "This member's self-service sign-up is unfinished; only they can finish it, by confirming their email. An import "
    "can't activate the account or verify its contacts"
)


class _Items:
    def __init__(self, member: MemberRecord, *, matched: str | None):
        self.member = member
        self.matched = matched
        verified = member.verified_contacts()
        self.last_verified = next(iter(verified)) if len(verified) == 1 else None
        self.items: list[dict] = []

    def add(self, code: str, ref: str, label: str, reason: str = "") -> None:
        self.items.append(
            {"id": f"{code}:{ref}", "code": code, "label": label, "enabled": not reason, "reason": reason}
        )

    def removal(self, code: str, contact, label: str) -> None:
        self.add(code, contact.id, label, self._removal_reason(contact))

    def _removal_reason(self, contact) -> str:
        if contact.id == self.matched:
            return MATCHED
        if contact.verified and contact.id == self.last_verified:
            return f"It is the only verified sign-in contact of {self.member.full_name or 'this member'}"
        return ""


def risky_items(values: dict, member: MemberRecord, snapshot: Snapshot, *, matched: str | None, actor=None):
    """The R-items of ``values`` (drops applied) when it updates ``member``; ``matched`` is the record matched on and
    ``actor`` the Admin the analysis is for (``None`` for a script)."""
    items = _Items(member, matched=matched)
    _secondaries(items, values, member, snapshot)
    _phones(items, values, member, snapshot)
    _flags(items, values, member, snapshot)
    _status(items, values, member, snapshot.objects.get(member.id), actor)
    return items.items


def _secondaries(items: _Items, values: dict, member: MemberRecord, snapshot: Snapshot) -> None:
    stored = member.emails_of_type("secondary")
    address = values.get("secondary_email")
    if not address:
        if values.get("has_secondary_email_column"):
            for contact in stored:
                items.removal("R1", contact, f"Remove secondary {contact.address} (the Secondary Email cell is blank)")
        return
    records = snapshot.email_records(address)
    if len(records) > 1:
        return
    record = records[0] if records else None
    named_is_secondary = record is not None and record.member == member.id and record.type == "secondary"
    if record is None or record.member is None or named_is_secondary:
        for contact in stored:
            if address_key(contact.address) != address_key(address):
                items.removal("R2", contact, f"Remove secondary {contact.address} (the sheet names {address})")


def _phones(items: _Items, values: dict, member: MemberRecord, snapshot: Snapshot) -> None:
    if not values.get("phone_number"):
        if values.get("has_phone_column"):
            for phone in member.phones:
                items.removal("R3", phone, f"Remove phone {phone.e164} (the Phone Number cell is blank)")
        return
    parsed = us_phone(values["phone_number"])
    if parsed is None or parsed[0] in snapshot.phones:
        return
    named = f"+{parsed[1].split('-')[0]}{parsed[0]}"
    for phone in member.phones:
        items.removal("R4", phone, f"Remove old phone {phone.e164} (the sheet names {named})")


def _owned_cells(values: dict, member: MemberRecord, snapshot: Snapshot):
    """(record, label, Verified cell, Subscribed cell) for each contact the row names that the member owns; a phone
    number's Verified cell is always None."""
    for column in ("primary", "secondary"):
        records = snapshot.email_records(values.get(f"{column}_email"))
        if len(records) == 1 and records[0].member == member.id:
            yield records[0], records[0].address, values.get(f"{column}_verified"), values.get(f"{column}_subscribed")
    parsed = us_phone(values.get("phone_number"))
    phone = snapshot.phones.get(parsed[0]) if parsed else None
    if phone is not None and phone.member == member.id:
        # No Verified cell: the Phone Verified column is ignored, so a number is never marked (un)verified (R6/R9).
        yield phone, phone.e164, None, values.get("phone_subscribed")


def _flags(items: _Items, values: dict, member: MemberRecord, snapshot: Snapshot) -> None:
    seen = set()
    for record, label, verified, subscribe in _owned_cells(values, member, snapshot):
        if record.id in seen:
            continue
        seen.add(record.id)
        if subscribe is True and not record.subscribe:
            items.add("R5", record.id, f"Re-subscribe {label}")
        if verified is False and record.verified:
            reason = ""
            if record.id == items.last_verified:
                reason = f"It is the only verified sign-in contact of {member.full_name or 'this member'}"
            items.add("R6", record.id, f"Mark {label} unverified", reason)
        if verified is True and not record.verified:
            reason = PENDING if member.registration_pending else ""
            items.add("R9", record.id, f"Mark {label} verified (it becomes a sign-in factor)", reason)


def _status(items: _Items, values: dict, member: MemberRecord, live, actor) -> None:
    """R7; ``live`` is the Member object the snapshot read (``None`` for a hand-built snapshot: the apply, which locks
    the members, still checks every ticked deactivation)."""
    active = values.get("is_active")
    if active is None or active == member.is_active:
        return
    if active:
        items.add("R7", member.id, "Reactivate the member", PENDING if member.registration_pending else "")
    else:
        # Only an Admin account can be refused: never your own, and never the last active Admin.
        targets = [live] if live is not None else []
        items.add("R7", member.id, "Deactivate the member", admin_removal_refusal(actor, targets, action=DEACTIVATE))
