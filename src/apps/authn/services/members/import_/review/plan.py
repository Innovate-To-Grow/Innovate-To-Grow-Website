"""Plan exactly what one row writes for the action chosen for it.

The same plan is shown under the selected choice on the review page, counted on the confirm page, and carried out by
the apply, which re-plans from freshly read records (the fingerprint check makes sure they are the ones reviewed).

An update writes, in this order: the profile fields the row changes; the Primary Email cell's flags (on that address
only, and only when the member owns it); a promotion, when chosen; the Secondary Email cell; the Phone Number cell;
the Active and Staff cells, when ticked; and last, the ticked removals. A new member is created as before: the
sheet's flags are trusted for a brand-new member's own email addresses. Its phone number is always saved unverified:
the Phone Verified column is ignored, because only the member's own one-time code may verify a number.
"""

from __future__ import annotations

from .actions import CREATE_CLAIM, SKIP, UPDATE, Action, Op, RowPlan
from .lookup import Snapshot, us_phone
from .plan_contacts import (
    ContactState,
    claimed_subscribe,
    plan_flags,
    plan_phone,
    plan_promote,
    plan_secondary,
)

PROFILE_FIELDS = ("first_name", "middle_name", "last_name", "title", "organization")
NAME_FIELDS = ("first_name", "middle_name", "last_name")
FIELD_LABELS = {
    "first_name": "First name",
    "middle_name": "Middle name",
    "last_name": "Last name",
    "title": "Title",
    "organization": "Organization",
}
ACTIVE_NOT_TICKED = (
    "Active is {sheet}, but the member is {state}; left {state} (activating or deactivating a member needs its tick)"
)
STAFF_IGNORED = "Staff column ignored (only an I2G Master may change staff status, with its tick)"
PENDING_NOTE = (
    "The member's self-service sign-up is unfinished; an import never activates it or verifies its contacts (only "
    "the person can, by confirming their email)"
)


def plan_row(values: dict, action: Action, snapshot: Snapshot, *, ticks=(), drops: dict | None = None) -> RowPlan:
    """The writes ``action`` makes for the row ``values``. ``drops`` are the cells the analysis set aside (V2, V4, V7,
    V8): ``{cell key: warning}``; they are reported as the row's warnings, not here."""
    drops = drops or {}
    values = apply_drops(values, drops)
    if action.kind == SKIP:
        return RowPlan(SKIP)
    if action.kind == UPDATE:
        return _plan_update(values, action, snapshot, set(ticks))
    return _plan_create(values, action, snapshot)


def apply_drops(values: dict, drops: dict) -> dict:
    """``values`` without the cells the analysis set aside. A dropped cell reads as a missing column, not a blank cell:
    a blank cell offers to remove what is stored, a dropped one leaves it alone."""
    values = dict(values)
    for key in drops:
        values[key] = None
    if "secondary_email" in drops:
        values["has_secondary_email_column"] = False
    if "phone_number" in drops:
        values["has_phone_column"] = False
    return values


def _plan_create(values: dict, action: Action, snapshot: Snapshot) -> RowPlan:
    plan = RowPlan(action.kind)
    fields = {name: values.get(name) or "" for name in PROFILE_FIELDS}
    active = values.get("is_active")
    fields["is_active"] = True if active is None else active
    fields["date_joined"] = values.get("date_joined")
    name = " ".join(fields[part] for part in NAME_FIELDS if fields[part])
    plan.add(
        Op("create_member", data=fields), f"Creates the member {name}{'' if fields['is_active'] else ' (inactive)'}"
    )
    verified, subscribe = values.get("primary_verified"), values.get("primary_subscribed")
    if action.kind == CREATE_CLAIM:
        record = next(c for c in snapshot.email_records(values["primary_email"]) if c.id == action.claim)
        verified = bool(verified)
        subscribe = claimed_subscribe(record, subscribe, column="Primary", plan=plan)
        plan.add(
            Op("claim_email", ref=record.id, data={"type": "primary", "verified": verified, "subscribe": subscribe}),
            f"Takes {record.address} (a contact email with no member) as the primary email ({_flags(verified, subscribe)})",
        )
    else:
        verified, subscribe = bool(verified), True if subscribe is None else subscribe
        data = {"address": values["primary_email"], "type": "primary", "verified": verified, "subscribe": subscribe}
        plan.add(Op("add_email", data=data), f"Primary email {values['primary_email']} ({_flags(verified, subscribe)})")
    _create_secondary(plan, values, snapshot)
    _create_phone(plan, values, snapshot)
    return plan


def _flags(verified: bool, subscribe: bool) -> str:
    return f"{'verified' if verified else 'unverified'}, {'subscribed' if subscribe else 'not subscribed'}"


def _create_secondary(plan: RowPlan, values: dict, snapshot: Snapshot) -> None:
    address = values.get("secondary_email")
    if not address:
        return
    records = snapshot.email_records(address)
    verified = bool(values.get("secondary_verified"))
    subscribe = values.get("secondary_subscribed")
    if not records:
        subscribe = True if subscribe is None else subscribe
        data = {"address": address, "type": "secondary", "verified": verified, "subscribe": subscribe, "demote": []}
        plan.add(Op("add_email", data=data), f"Secondary email {address} ({_flags(verified, subscribe)})")
    elif len(records) == 1 and records[0].member is None:
        record = records[0]
        subscribe = claimed_subscribe(record, subscribe, column="Secondary", plan=plan)
        data = {"type": "secondary", "verified": False, "subscribe": subscribe, "demote": []}
        plan.add(
            Op("claim_email", ref=record.id, data=data),
            f"Attaches {address} (a contact email with no member) as the secondary email ({_flags(False, subscribe)})",
        )
    else:
        holder = snapshot.member(records[0].member) if len(records) == 1 else None
        who = holder.label if holder else f"{len(records)} contact emails that differ only in letter case"
        plan.notes.append(f"Secondary Email {address} is already used by {who}; not added")


def _create_phone(plan: RowPlan, values: dict, snapshot: Snapshot) -> None:
    parsed = us_phone(values.get("phone_number"))
    if parsed is None:
        return
    national, region = parsed
    e164 = f"+{region.split('-')[0]}{national}"
    record = snapshot.phones.get(national)
    if record is None:
        subscribe = bool(values.get("phone_subscribed"))
        data = {"number": national, "region": region, "subscribe": subscribe}
        plan.add(Op("add_phone", data=data), f"Phone {e164} ({_flags(False, subscribe)})")
        return
    holder = snapshot.member(record.member) if record.member else None
    who = holder.label if holder else "a contact phone that is not linked to any member"
    plan.notes.append(f"Phone Number {e164} is already used by {who}; not added")


def _plan_update(values: dict, action: Action, snapshot: Snapshot, ticks: set[str]) -> RowPlan:
    member = snapshot.member(action.target)
    plan = RowPlan(UPDATE, target=member.id)
    state = ContactState(member)
    _plan_profile(plan, values, member, keep_name=action.keep_name)
    owned = [c for c in snapshot.email_records(values.get("primary_email")) if c.member == member.id]
    record = owned[0] if owned else None
    if action.claim:
        _plan_attach(plan, state, values, snapshot, action.claim)
    elif record is not None:
        plan_flags(plan, state, record, "Primary", (values["primary_verified"], values["primary_subscribed"]), ticks)
    elif values.get("primary_email"):
        plan.notes.append(_not_owned_note(values["primary_email"], snapshot, member))
    if action.make_primary and record is not None:
        plan_promote(plan, state, record)
    plan_secondary(plan, state, values, snapshot, ticks, matched=record.id if record else action.claim)
    plan_phone(plan, state, values, snapshot, ticks)
    _plan_status(plan, values, member, ticks)
    for op, change, listed, label in state.removals:
        plan.add(op, change)
        plan.listed[listed].append(label)
    _check_last_contact(plan, state, member)
    if member.privileged and plan.writes:
        # Spelled out on the confirm page: a staff or superuser account is a sign-in to the admin.
        plan.listed["privileged_changes"].append(f"{member.label}: {'; '.join(plan.changes)}")
    return plan


def _plan_profile(plan: RowPlan, values: dict, member, *, keep_name: bool) -> None:
    """Overwrite the profile fields the row fills in; a blank cell keeps the stored value."""
    names = NAME_FIELDS if keep_name else ()
    changed = {
        name: values[name]
        for name in PROFILE_FIELDS
        if name not in names and values.get(name) and values[name] != getattr(member, name)
    }
    if changed:
        lines = [f"{FIELD_LABELS[name]}: {getattr(member, name)!r} → {value!r}" for name, value in changed.items()]
        plan.add(Op("profile", ref=member.id, data=changed), "; ".join(lines))
    if keep_name and any(values.get(name) and values[name] != getattr(member, name) for name in NAME_FIELDS):
        plan.notes.append(f"The sheet's name is not applied; {member.full_name or 'the stored name'} is kept")


def _plan_attach(plan: RowPlan, state: ContactState, values: dict, snapshot: Snapshot, claim: str) -> None:
    """Attach the Primary Email cell's unlinked address to the member, unverified, as secondary (or "other")."""
    record = next(c for c in snapshot.email_records(values["primary_email"]) if c.id == claim)
    email_type = "other" if state.of_type("secondary") else "secondary"
    subscribe = claimed_subscribe(
        record,
        values.get("primary_subscribed"),
        column="Primary",
        plan=plan,
        allowed=state.any_email_subscribed(),
        refusal=f"{record.address} is attached unsubscribed: the member is unsubscribed at every other address",
    )
    data = {"type": email_type, "verified": False, "subscribe": subscribe, "demote": []}
    plan.add(
        Op("claim_email", ref=record.id, data=data),
        f'Attaches {record.address} (a contact email with no member) as "{email_type}" ({_flags(False, subscribe)})',
    )
    state.types[record.id] = email_type
    state.addresses[record.id] = record.address
    state.created[record.id] = record.created
    state.subscribed[record.id] = subscribe
    state.verified[record.id] = False


def _not_owned_note(address: str, snapshot: Snapshot, member) -> str:
    records = snapshot.email_records(address)
    holders = {c.member for c in records}
    if not records:
        where = "is not one of the member's addresses"
    elif holders == {None}:
        where = "is a contact email with no member"
    else:
        others = [snapshot.member(h).label for h in holders if h and snapshot.member(h)]
        where = f"belongs to {', '.join(others)}" if others else "belongs to another member"
    return (
        f"Primary Email {address} {where}; it is not added to {member.label}, and its Verified/Subscribed cells are "
        "ignored"
    )


def _plan_status(plan: RowPlan, values: dict, member, ticks: set[str]) -> None:
    active = values.get("is_active")
    if active and not member.is_active and member.registration_pending:
        # Only the person finishes their own sign-up (by confirming their email); never an import, tick or not.
        plan.notes.append(PENDING_NOTE)
        active = None
    if active is not None and active != member.is_active:
        if f"R7:{member.id}" in ticks:
            change = "Reactivates the member" if active else "Deactivates the member"
            plan.add(Op("active", ref=member.id, data={"value": active}), change)
            plan.listed["active_changes"].append(f"{member.label}: {'reactivated' if active else 'deactivated'}")
        else:
            sheet, state = ("TRUE", "inactive") if active else ("FALSE", "active")
            plan.notes.append(ACTIVE_NOT_TICKED.format(sheet=sheet, state=state))
    staff = values.get("is_staff")
    if staff is not None and staff != member.is_staff:
        if f"R8:{member.id}" in ticks:
            plan.add(
                Op("staff", ref=member.id, data={"value": staff}),
                "Grants staff status" if staff else "Removes staff status",
            )
            plan.listed["staff_changes"].append(f"{member.label}: staff {'granted' if staff else 'removed'}")
        else:
            plan.notes.append(STAFF_IGNORED)


def _check_last_contact(plan: RowPlan, state: ContactState, member) -> None:
    """No choice may leave a member who has a verified sign-in contact without one (``services/account/recovery``)."""
    if member.verified_contacts() and not state.verified_ids():
        plan.problems.append(
            f"These ticks would remove the last verified sign-in contact of {member.label}; untick one of them"
        )
