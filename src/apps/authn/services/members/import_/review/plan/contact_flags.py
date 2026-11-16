"""A contact's flags in a plan: its state, and whether it starts verified and subscribed."""

from __future__ import annotations

from ..lookup.records import MemberRecord
from .actions import Op, RowPlan


class ContactState:
    """A member's contacts as the planned writes leave them."""

    def __init__(self, member: MemberRecord):
        self.member = member
        self.types = {email.id: email.type for email in member.emails}
        self.addresses = {email.id: email.address for email in member.emails}
        self.created = {email.id: email.created for email in member.emails}
        self.subscribed = {email.id: email.subscribe for email in member.emails}
        self.verified = {contact.id: contact.verified for contact in [*member.emails, *member.phones]}
        self.phone_subscribed = {phone.id: phone.subscribe for phone in member.phones}
        self.deleted: set[str] = set()
        self.removals: list[tuple[Op, str, str, str]] = []

    def of_type(self, email_type: str, exclude: str | None = None) -> list[str]:
        """Email ids of ``email_type``, newest first (the order ``ContactEmail.Meta.ordering`` gives)."""
        ids = [i for i, kind in self.types.items() if kind == email_type and i != exclude and i not in self.deleted]
        return sorted(ids, key=lambda i: (self.created[i], i), reverse=True)

    def verified_ids(self) -> set[str]:
        return {contact for contact, verified in self.verified.items() if verified and contact not in self.deleted}

    def any_email_subscribed(self) -> bool:
        return any(on for contact, on in self.subscribed.items() if contact not in self.deleted)

    def remove(self, kind: str, contact: str, label: str, listed: str) -> None:
        if contact in self.deleted:
            return
        self.deleted.add(contact)
        self.removals.append((Op(kind, ref=contact), f"Removes {label}", listed, label))


def _flags_suffix(verified: bool, subscribe: bool) -> str:
    return f"{'verified' if verified else 'unverified'}, {'subscribed' if subscribe else 'not subscribed'}"


def new_contact_subscribe(sheet_value, *, default: bool, allowed: bool, refusal: str, plan: RowPlan) -> bool:
    """Subscribed flag for a contact added to an existing member.

    The sheet's value, else the model default; but never on when the member has opted out on that channel (no
    subscribed address, or only unsubscribed phone numbers), as the event-registration email sync also decides.
    """
    wanted = default if sheet_value is None else sheet_value
    if wanted and not allowed:
        if sheet_value:
            plan.notes.append(f"{refusal} (re-subscribing needs the person's consent)")
        return False
    return wanted


def claimed_subscribe(
    record, sheet_value, *, column: str, plan: RowPlan, allowed: bool = True, refusal: str = ""
) -> bool:
    """Subscribed flag for a contact email with no member that a row takes (a new member's primary, or attached).

    The record keeps its own flag, which the cell can turn off (an opt-out) but never on: an unsubscribed record may
    carry the person's earlier opt-out, and an import never re-subscribes anyone without a tick (there is none for a
    record no member owns yet). A subscribed record then follows ``new_contact_subscribe`` with ``allowed``.
    """
    if not record.subscribe:
        if sheet_value is True:
            plan.notes.append(
                f"{column} Subscribed is TRUE, but {record.address} is unsubscribed; left unsubscribed (an import never "
                "re-subscribes an address; with the person's consent, re-subscribe it under Contact Emails)"
            )
        return False
    return new_contact_subscribe(sheet_value, default=True, allowed=allowed, refusal=refusal, plan=plan)


def plan_flags(plan: RowPlan, state: ContactState, record, column: str, cells: tuple, ticks: set[str]) -> None:
    """Apply a contact's Verified/Subscribed cells (``cells``) to ``record``, an email or phone the member owns. A phone
    number's Verified cell is always None (the column is ignored)."""
    verified, subscribe = cells
    kind, label = ("phone_flags", record.e164) if hasattr(record, "e164") else ("email_flags", record.address)
    data, changes = {}, []
    _verified_cell(plan, state, record, (column, label), verified, ticks, data, changes)
    _subscribed_cell(plan, record, (column, label), subscribe, ticks, data, changes)
    if data:
        plan.ops.append(Op(kind, ref=record.id, data=data))
        plan.changes.extend(changes)
        if "verified" in data:
            state.verified[record.id] = data["verified"]
        if "subscribe" in data and kind == "email_flags":
            state.subscribed[record.id] = data["subscribe"]


def _verified_cell(plan, state, record, names: tuple, verified, ticks: set[str], data: dict, changes: list) -> None:
    """TRUE verifies with the R9 tick (never on an unfinished sign-up); FALSE un-verifies with the R6 tick."""
    column, label = names
    if verified is True and not record.verified:
        if state.member.registration_pending:
            plan.notes.append(
                f"{column} Verified is TRUE, but {label} belongs to an unfinished sign-up; left unverified"
            )
        elif f"R9:{record.id}" in ticks:
            data["verified"] = True
            changes.append(f"Marks {label} verified")
            plan.listed["verified"].append(label)
        else:
            plan.notes.append(
                f"{column} Verified is TRUE, but {label} is unverified; left unverified (verifying makes it a sign-in "
                "factor and needs its tick)"
            )
    elif verified is False and record.verified:
        if f"R6:{record.id}" in ticks:
            data["verified"] = False
            changes.append(f"Marks {label} unverified")
            plan.listed["unverified"].append(label)
        else:
            plan.notes.append(
                f"{column} Verified is FALSE, but {label} is verified; left verified (un-verifying needs its tick)"
            )


def _subscribed_cell(plan, record, names: tuple, subscribe, ticks: set[str], data: dict, changes: list) -> None:
    """FALSE unsubscribes (an opt-out); TRUE re-subscribes only with the R5 tick."""
    column, label = names
    if subscribe is False and record.subscribe:
        data["subscribe"] = False
        changes.append(f"Unsubscribes {label}")
    elif subscribe is True and not record.subscribe:
        if f"R5:{record.id}" in ticks:
            data["subscribe"] = True
            changes.append(f"Re-subscribes {label}")
            plan.listed["resubscribed"].append(label)
        else:
            plan.notes.append(
                f"{column} Subscribed is TRUE, but {label} is unsubscribed; left unsubscribed (re-subscribing needs "
                "the person's consent and its tick)"
            )
