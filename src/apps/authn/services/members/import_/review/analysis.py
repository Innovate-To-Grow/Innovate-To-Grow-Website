"""Work out what each row of a sheet would do, without writing anything.

A row resolves in this order: its Member UUID (when the sheet has one), then its Primary Email cell, looked up in every
role (a member's primary, secondary or "other" address, or a contact email with no member), then a new member. Each
row ends as ``invalid`` (cannot import), ``needs_decision`` (one conflict, C1–C9, shown in the precedence of
``describe.PRECEDENCE``), ``ready_create``, ``ready_update`` or ``no_change``. A row that needs a decision is skipped
until an admin chooses otherwise. The review is the plan: the apply re-runs this analysis on freshly read records and
applies nothing if any row's records changed (``fingerprint``).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from apps.authn.models import Member

from ..contacts import valid_new_address
from .actions import CREATE, CREATE_CLAIM, SKIP, UPDATE, Action, resolve_action
from .choices import OptionContext, names_match, options_for, ready_options
from .describe import describe_action, why
from .grouping import cross_row_drops, duplicate_groups
from .lookup import Snapshot, fingerprint, row_slice, us_phone
from .plan import apply_drops, plan_row
from .risky import risky_items

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
# Conflicts that come before "the same person appears twice" (C1) in precedence: a row with one is never grouped.
_BEFORE_C1 = frozenset({"privileged_target", "ambiguous_address", "uuid_email_mismatch", "uuid_not_found"})


@dataclass
class Context:
    """Who the analysis is for: the upload's mode and the actor's rights."""

    mode: str = UPDATE_EXISTING
    is_master: bool = False
    can_update: bool = True
    can_manage: Callable[[object], bool] = field(default=lambda member: True)


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


@dataclass
class RowAnalysis:
    values: dict
    status: str
    conflict: str = ""
    facts: dict = field(default_factory=dict)
    options: list[dict] = field(default_factory=list)
    default: str = SKIP
    warnings: list[dict] = field(default_factory=list)
    risky: dict = field(default_factory=dict)
    slice: dict = field(default_factory=dict)
    fingerprint: str = ""

    @property
    def row_number(self) -> int:
        return self.values["row"]

    @property
    def target(self) -> str | None:
        return self.facts.get("target")

    @property
    def drops(self) -> dict:
        return self.facts.get("drops", {})


def analyse_rows(rows: list[dict], snapshot: Snapshot, ctx: Context) -> list[RowAnalysis]:
    """Analyse parsed ``rows`` against ``snapshot`` (``lookup.load_snapshot(rows)``)."""
    # Resolving reads no Secondary Email or Phone Number cell, so it comes first: a row that can't be imported then
    # never takes a cell another row could add (V8).
    resolutions = [resolve_row(row, snapshot, ctx) for row in rows]
    invalid = {row["row"] for row, resolution in zip(rows, resolutions, strict=True) if resolution.status == INVALID}
    drops = cross_row_drops(rows, snapshot, invalid)
    groups = duplicate_groups(rows, resolutions)
    return [
        _finish(row, resolution, snapshot, ctx, drops=drops.get(row["row"], {}), group=groups.get(row["row"], []))
        for row, resolution in zip(rows, resolutions, strict=True)
    ]


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
    member = snapshot.objects.get(target.id) or target
    if not ctx.can_manage(member):
        return Resolution(NEEDS_DECISION, "privileged_target", **base)
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
        "privileged_target": "Only an I2G Master may change staff and superuser accounts",
    }
    return None, reasons.get(resolution.conflict, "This row needs its own decision")


def _finish(values, resolution: Resolution, snapshot: Snapshot, ctx: Context, *, drops: dict, group: list[int]):
    facts = {
        "target": resolution.target,
        "matched_by": resolution.matched_by,
        "record": resolution.record,
        "uuid_member": resolution.uuid_member,
        "email_member": resolution.email_member,
        "drops": drops,
        "group": group,
        "invalid": resolution.invalid,
    }
    analysis = RowAnalysis(values=values, status=resolution.status, facts=facts)
    analysis.warnings = [*values.get("warnings", []), *drops.values()]
    if resolution.status == INVALID:
        return _seal(analysis, snapshot)
    conflict = "duplicate_in_sheet" if group and resolution.conflict not in _BEFORE_C1 else resolution.conflict
    dropped = apply_drops(values, drops)
    oc = OptionContext(snapshot, ctx, dropped)
    if conflict:
        _decision(analysis, conflict, resolution, oc, ctx)
    else:
        target = snapshot.member(resolution.target)
        analysis.options = ready_options(resolution.status, target.label if target else "")
        analysis.default = analysis.options[0]["value"]
        if (
            resolution.status == READY_UPDATE
            and not plan_row(values, resolve_action("update", facts), snapshot, drops=drops).writes
        ):
            analysis.status = NO_CHANGE
    analysis.risky = _risky(analysis, dropped, snapshot, ctx)
    return _seal(analysis, snapshot)


def _decision(analysis: RowAnalysis, conflict: str, resolution: Resolution, oc: OptionContext, ctx: Context) -> None:
    analysis.status, analysis.conflict = NEEDS_DECISION, conflict
    facts, values, snapshot = analysis.facts, oc.values, oc.snapshot
    if conflict == "exists_but_skip_mode" and ctx.mode == UPDATE_EXISTING and not ctx.can_update:
        facts["no_permission"] = True
    if conflict == "duplicate_in_sheet":
        solo, reason = suggested_action(resolution, values, ctx)
        facts.update(solo=solo.as_dict() if solo else None, solo_reason=reason)
        facts["solo_text"] = describe_action(solo, snapshot, values) if solo else ""
    if conflict == "uuid_not_found":
        fallback_resolution = resolve_row(values, snapshot, ctx, use_uuid=False)
        fallback, reason = suggested_action(fallback_resolution, values, ctx)
        if fallback_resolution.status == INVALID:
            fallback, reason = None, fallback_resolution.invalid
        facts.update(fallback=fallback.as_dict() if fallback else None, fallback_reason=reason)
        facts["fallback_text"] = describe_action(fallback, snapshot, values) if fallback else ""
    if conflict == "unlinked_address":
        facts["attach_candidates"] = _attach_candidates(values, snapshot, resolution)
    analysis.options = options_for(conflict, facts, oc)
    analysis.default = SKIP
    facts["why"] = why(conflict, values, snapshot, **facts)


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


def update_targets(analysis: RowAnalysis) -> list[str]:
    """Each member one of the row's options would update."""
    targets = []
    for item in analysis.options:
        action = resolve_action(item["value"], analysis.facts)
        if action.kind == UPDATE and action.target and action.target not in targets:
            targets.append(action.target)
    return targets


def _risky(analysis: RowAnalysis, dropped: dict, snapshot: Snapshot, ctx: Context) -> dict:
    items = {}
    for target in update_targets(analysis):
        member = snapshot.member(target)
        owned = [c.id for c in snapshot.email_records(dropped.get("primary_email")) if c.member == target]
        found = risky_items(dropped, member, snapshot, matched=owned[0] if owned else None, is_master=ctx.is_master)
        if found:
            items[target] = found
    return items


def _seal(analysis: RowAnalysis, snapshot: Snapshot) -> RowAnalysis:
    analysis.slice = row_slice(snapshot, analysis.values)
    analysis.fingerprint = fingerprint(analysis.slice)
    return analysis
