"""Plan the writes of a row that creates a member (or claims an unlinked address for one)."""

from __future__ import annotations

from ..lookup.records import Snapshot, us_phone
from .actions import CREATE_CLAIM, Action, Op, RowPlan
from .contact_flags import claimed_subscribe
from .fields import NAME_FIELDS, PROFILE_FIELDS


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
