"""Risky changes: what a row may do to the member it updates only when the admin ticks it (R1–R9).

Each item is its own tick, off by default, so every deletion, re-subscription, un-verification and verification is a
separate decision. Verifying (R9) is one too: a verified contact is a working sign-in factor (an email code, or an SMS
password reset), so a sheet never creates one without a tick. An item that may not be ticked stays visible with the
reason: the address the row was matched on, the member's only verified sign-in contact (the rule of
``services/account/recovery.py``), an account only an I2G Master may change, or a self-service sign-up the person has
not finished (only they can finish it, by confirming their email). The planner re-checks the ticks together against
the last-sign-in-contact rule.
"""

from __future__ import annotations

from .lookup import MemberRecord, Snapshot, address_key, us_phone

RISKY_TYPES = {
    "R1": "Remove secondary emails: the Secondary Email cell is blank",
    "R2": "Remove the member's other secondary emails",
    "R3": "Remove phone numbers: the Phone Number cell is blank",
    "R4": "Remove the old phone numbers the sheet's number replaces",
    "R5": "Re-subscribe (only with the person's consent)",
    "R6": "Mark contacts unverified",
    "R7": "Deactivate or reactivate members",
    "R8": "Grant or remove staff status (I2G Master only)",
    "R9": "Mark contacts verified (each becomes a sign-in factor)",
}
MATCHED = "This is the address the row was matched on"
PRIVILEGED = "Only an I2G Master may change staff and superuser accounts"
MASTER_ONLY = "Only an I2G Master may change staff status"
PENDING = (
    "This member's self-service sign-up is unfinished; only they can finish it, by confirming their email. An import "
    "can't activate the account or verify its contacts"
)


class _Items:
    def __init__(self, member: MemberRecord, *, matched: str | None, may_change_privileged: bool):
        self.member = member
        self.matched = matched
        self.may_change_privileged = may_change_privileged
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
        if self.member.privileged and not self.may_change_privileged:
            return PRIVILEGED
        return ""


def risky_items(values: dict, member: MemberRecord, snapshot: Snapshot, *, matched: str | None, is_master: bool):
    """The R-items of ``values`` (drops applied) when it updates ``member``; ``matched`` is the record matched on."""
    items = _Items(member, matched=matched, may_change_privileged=is_master)
    _secondaries(items, values, member, snapshot)
    _phones(items, values, member, snapshot)
    _flags(items, values, member, snapshot)
    _status(items, values, member, is_master)
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
    """(record, label, Verified cell, Subscribed cell) for each contact the row names that the member owns."""
    for column in ("primary", "secondary"):
        records = snapshot.email_records(values.get(f"{column}_email"))
        if len(records) == 1 and records[0].member == member.id:
            yield records[0], records[0].address, values.get(f"{column}_verified"), values.get(f"{column}_subscribed")
    parsed = us_phone(values.get("phone_number"))
    phone = snapshot.phones.get(parsed[0]) if parsed else None
    if phone is not None and phone.member == member.id:
        yield phone, phone.e164, values.get("phone_verified"), values.get("phone_subscribed")


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
            items.add("R9", record.id, f"Mark {label} verified (it becomes a sign-in factor)", _verify_reason(items))


def _verify_reason(items: _Items) -> str:
    if items.member.registration_pending:
        return PENDING
    if items.member.privileged and not items.may_change_privileged:
        return PRIVILEGED
    return ""


def _status(items: _Items, values: dict, member: MemberRecord, is_master: bool) -> None:
    active = values.get("is_active")
    if active is not None and active != member.is_active:
        label = "Reactivate the member" if active else "Deactivate the member"
        reason = "" if is_master or not member.privileged else PRIVILEGED
        if active and member.registration_pending:
            reason = PENDING
        items.add("R7", member.id, label, reason)
    staff = values.get("is_staff")
    if staff is not None and staff != member.is_staff:
        label = "Grant staff status" if staff else "Remove staff status"
        items.add("R8", member.id, label, "" if is_master else MASTER_ONLY)
