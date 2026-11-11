"""Plan what one row does to the contacts of the member it updates.

Without a tick a row never deletes, re-subscribes, un-verifies or verifies anything: a blank cell keeps every stored
contact, a new address or number is added next to the old ones (unverified), and an address or number another member
holds is never moved. The flag cells apply only to the contact the cell names, and only when the member owns it: FALSE
unsubscribes (an opt-out); TRUE verifies (R9), FALSE un-verifies (R6) and TRUE re-subscribes (R5) only when ticked.
Removals (R1–R4) are planned here and written last, after every addition.

``ContactState`` follows the member's contacts through the planned writes, so a later step sees an earlier one (a
promotion demotes the old primary before the Secondary cell is read) and the last-sign-in-contact rule can be checked
against the outcome.
"""

from __future__ import annotations

from .actions import Op, RowPlan
from .lookup import EmailRecord, MemberRecord, Snapshot, us_phone

NEVER_MOVES = "an import never moves a contact from one member to another"
STARTS_UNVERIFIED = "contacts added to an existing member start unverified; the member verifies them on /account"
KEPT_UNLESS_TICKED = "nothing is removed unless its removal is ticked in the review"


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


def plan_flags(plan: RowPlan, state: ContactState, record, column: str, cells: tuple, ticks: set[str]) -> None:
    """Apply a contact's Verified/Subscribed cells (``cells``) to ``record``, an email or phone the member owns."""
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


def plan_promote(plan: RowPlan, state: ContactState, record: EmailRecord) -> None:
    """Make ``record`` the primary with ``make_contact_email_primary``'s demotions; nothing is deleted."""
    if state.types.get(record.id) == "primary":
        return
    if not state.verified.get(record.id):
        plan.problems.append(
            f"{record.address} can't be made the primary email while it is unverified; untick its un-verify box"
        )
        return
    details = []
    old_primary = next(iter(state.of_type("primary", exclude=record.id)), None)
    if old_primary:
        secondary = next(iter(state.of_type("secondary", exclude=record.id)), None)
        if secondary:
            state.types[secondary] = "other"
            details.append(f'the previous secondary {state.addresses[secondary]} becomes "other"')
        state.types[old_primary] = "secondary"
        details.insert(0, f"the previous primary {state.addresses[old_primary]} becomes secondary")
    state.types[record.id] = "primary"
    change = "; ".join([f"Makes {record.address} the primary email", *details, "nothing is deleted"])
    plan.ops.append(Op("promote", ref=record.id))
    plan.changes.append(change)
    plan.listed["primary_changes"].append(f"{record.address} made primary")


def _holder_note(column: str, label: str, holders, snapshot: Snapshot) -> str:
    owner = snapshot.member(holders.member) if holders.member else None
    if owner is None:
        return f"{column} {label} is a contact with no member; not added (link it under Contact Emails or Phones)"
    return f"{column} {label} belongs to {owner.label}; not added ({NEVER_MOVES})"


def plan_secondary(plan, state, values: dict, snapshot: Snapshot, ticks: set[str], matched: str | None) -> None:
    """The Secondary Email cell: keep, add, attach or flag; R1/R2 removals only when ticked."""
    member = state.member
    stored = member.emails_of_type("secondary")
    address = values.get("secondary_email")
    if not address:
        if values.get("has_secondary_email_column") and stored:
            _blank_removals(plan, state, stored, "R1", ticks, "Secondary Email")
        return
    records = snapshot.email_records(address)
    if len(records) > 1:
        plan.notes.append(
            f"Secondary Email {address} matches {len(records)} contact emails that differ only in letter case; not "
            "added (merge them under Contact Emails)"
        )
        return
    record = records[0] if records else None
    if record is not None and record.member not in (None, member.id):
        plan.notes.append(_holder_note("Secondary Email", address, record, snapshot))
        return
    if record is None or record.member is None:
        _add_secondary(plan, state, values, address, record, ticks, stored)
        return
    plan_flags(plan, state, record, "Secondary", (values["secondary_verified"], values["secondary_subscribed"]), ticks)
    if state.types.get(record.id) != "secondary":
        plan.notes.append(
            f'Secondary Email {address} is already this member\'s "{state.types.get(record.id)}" email; left as it is'
        )
        return
    for other in stored:
        if other.id != record.id and other.id != matched and f"R2:{other.id}" in ticks:
            state.remove("delete_email", other.id, f"secondary {other.address}", "emails_deleted")


def _blank_removals(plan, state, stored, code: str, ticks: set[str], column: str) -> None:
    kept = []
    for contact in stored:
        label = getattr(contact, "address", None) or contact.e164
        if f"{code}:{contact.id}" in ticks:
            kind = "delete_email" if hasattr(contact, "address") else "delete_phone"
            listed = "emails_deleted" if kind == "delete_email" else "phones_deleted"
            prefix = "secondary " if kind == "delete_email" else "phone "
            state.remove(kind, contact.id, f"{prefix}{label}", listed)
        else:
            kept.append(label)
    if kept:
        plan.notes.append(f"{column} is blank; kept {', '.join(kept)} ({KEPT_UNLESS_TICKED})")


def _add_secondary(plan, state, values, address, record, ticks, stored) -> None:
    """Add (or attach an unlinked) secondary; the current secondaries become "other" unless their removal is ticked."""
    removed = {other.id for other in stored if f"R2:{other.id}" in ticks}
    demote = [contact for contact in state.of_type("secondary") if contact not in removed]
    subscribe = new_contact_subscribe(
        values.get("secondary_subscribed"),
        default=True if record is None else record.subscribe,
        allowed=state.any_email_subscribed(),
        refusal=f"{address} is added unsubscribed: the member is unsubscribed at every other address",
        plan=plan,
    )
    data = {"type": "secondary", "verified": False, "subscribe": subscribe, "demote": demote}
    if record is None:
        plan.ops.append(Op("add_email", data={"address": address, **data}))
        change = f"Adds {address} as the secondary email ({_flags_suffix(False, subscribe)})"
    else:
        plan.ops.append(Op("claim_email", ref=record.id, data=data))
        change = f"Attaches {address} (a contact email with no member) as the secondary email ({_flags_suffix(False, subscribe)})"
    for contact in demote:
        state.types[contact] = "other"
    if demote:
        change += "; the previous secondary " + ", ".join(state.addresses[c] for c in demote) + ' becomes "other"'
    plan.changes.append(change)
    if values.get("secondary_verified"):
        plan.notes.append(f"{address} is added unverified ({STARTS_UNVERIFIED})")
    for other in stored:
        if other.id in removed:
            state.remove("delete_email", other.id, f"secondary {other.address}", "emails_deleted")


def plan_phone(plan, state, values: dict, snapshot: Snapshot, ticks: set[str]) -> None:
    """The Phone Number cell: keep, add or flag; R3/R4 removals only when ticked."""
    member = state.member
    if not values.get("phone_number"):
        if values.get("has_phone_column") and member.phones:
            _blank_removals(plan, state, member.phones, "R3", ticks, "Phone Number")
        return
    parsed = us_phone(values["phone_number"])
    if parsed is None:
        plan.notes.append(f"Phone Number {values['phone_number']} is not a 10-digit US number; ignored")
        return
    national, region = parsed
    record = snapshot.phones.get(national)
    e164 = f"+{region.split('-')[0]}{national}"
    if record is not None and record.member != member.id:
        plan.notes.append(_holder_note("Phone Number", e164, record, snapshot))
        return
    if record is not None:
        plan_flags(plan, state, record, "Phone", (values["phone_verified"], values["phone_subscribed"]), ticks)
        return
    subscribe = new_contact_subscribe(
        values.get("phone_subscribed"),
        default=False,
        allowed=not member.phones or any(state.phone_subscribed.values()),
        refusal=f"{e164} is added unsubscribed: the member's other phone numbers are unsubscribed",
        plan=plan,
    )
    plan.ops.append(Op("add_phone", data={"number": national, "region": region, "subscribe": subscribe}))
    kept = [phone for phone in member.phones if f"R4:{phone.id}" not in ticks]
    change = f"Adds phone {e164} ({_flags_suffix(False, subscribe)})"
    if kept:
        change += f"; keeps {', '.join(phone.e164 for phone in kept)} (an import never replaces a number in place)"
    plan.changes.append(change)
    if values.get("phone_verified"):
        plan.notes.append(f"{e164} is added unverified ({STARTS_UNVERIFIED})")
    for phone in member.phones:
        if f"R4:{phone.id}" in ticks:
            state.remove("delete_phone", phone.id, f"phone {phone.e164}", "phones_deleted")
