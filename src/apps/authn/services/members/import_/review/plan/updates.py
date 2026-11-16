"""Plan the writes of a row that updates an existing member: profile, contacts, attaches and status."""

from __future__ import annotations

from ..lookup.records import Snapshot
from .actions import UPDATE, Action, Op, RowPlan
from .contact_flags import ContactState, claimed_subscribe, plan_flags
from .contact_plans import plan_phone, plan_promote, plan_secondary
from .creates import _flags
from .fields import ACTIVE_NOT_TICKED, FIELD_LABELS, NAME_FIELDS, PENDING_NOTE, PROFILE_FIELDS, STAFF_IGNORED


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
