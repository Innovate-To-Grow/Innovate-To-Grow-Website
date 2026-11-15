"""The choices a review offers for each row, and which of them a bulk control may set.

Every row that needs a decision starts on "Skip this row": nothing happens to a conflict until an admin picks a choice
for it. The choice the import plan suggests is marked, so it is one click away. A choice that is not allowed stays
visible but disabled, with the reason. The server accepts only a choice from the row's own list (a forged POST fails)
and checks it again at apply.
"""

from __future__ import annotations

from .actions import SKIP
from .lookup import Snapshot
from .names import names_agree

NO_CHANGE_PERMISSION = "You do not have permission to change members"
PRIVILEGED = "Only an I2G Master may change staff and superuser accounts"
NEEDS_NAMES = "A new member needs a first and a last name; fill them in the sheet"
# The bulk choices of each conflict: only those an admin may set for a whole group without looking at each row.
BULK_CHOICES = {
    "duplicate_in_sheet": ("use_first", SKIP),
    "privileged_target": (),
    "ambiguous_address": (SKIP,),
    "uuid_email_mismatch": (SKIP,),
    "uuid_not_found": ("ignore_uuid", SKIP),
    "name_differs": (SKIP,),
    "address_not_primary": ("update", "update_make_primary", SKIP),
    "unlinked_address": ("create_claim", SKIP),
    "exists_but_skip_mode": (SKIP, "update"),
}
BULK_LABELS = {
    "use_first": "Use the first usable row of every repeat group",
    SKIP: "Skip",
    "ignore_uuid": "Ignore the Member UUID and match by email",
    "update": "Update the member",
    "update_make_primary": "Update the member and make the address their primary (where it is verified)",
    "create_claim": "Create a new member with the address (where the row has both names)",
}


def option(value: str, label: str, *, reason: str = "", hint: str = "", suggested: bool = False) -> dict:
    return {
        "value": value,
        "label": label,
        "hint": hint,
        "enabled": not reason,
        "reason": reason,
        "suggested": suggested,
    }


def skip_option(hint: str = "") -> dict:
    return option(SKIP, "Skip this row", hint=hint or "Nothing is written for this row.")


class OptionContext:
    """What the option builders need: the snapshot, the actor's rights and the row."""

    def __init__(self, snapshot: Snapshot, ctx, values: dict):
        self.snapshot = snapshot
        self.ctx = ctx
        self.values = values

    def member(self, member_id):
        return self.snapshot.member(member_id)

    def update_reason(self, member_id) -> str:
        """Why the actor may not update ``member_id`` (``""`` when they may)."""
        if not self.ctx.can_update:
            return NO_CHANGE_PERMISSION
        member = self.snapshot.objects.get(member_id) or self.member(member_id)
        if member is not None and not self.ctx.can_manage(member):
            return PRIVILEGED
        return ""

    @property
    def has_names(self) -> bool:
        return bool(self.values.get("first_name") and self.values.get("last_name"))


def options_for(conflict: str, facts: dict, oc: OptionContext) -> list[dict]:
    """The options of a row that needs a decision; ``facts`` are the analysis's findings for it."""
    return _BUILDERS[conflict](facts, oc)


def _duplicate(facts, oc):
    solo = facts.get("solo_text")
    reason = "" if facts.get("solo") else facts.get("solo_reason") or "This row would be skipped on its own"
    return [
        option("use_row", "Use this row", reason=reason, hint=f"Apply this row: {solo}" if solo else ""),
        skip_option("Skip this row; another row of the group may be used."),
    ]


def _privileged(facts, oc):
    return [option(SKIP, "Skip this row", hint=PRIVILEGED)]


def _ambiguous(facts, oc):
    options = []
    records = oc.snapshot.email_records(oc.values.get("primary_email"))
    owned_by_member = any(record.member for record in records)
    for record in records:
        if record.member:
            member = oc.member(record.member)
            options.append(
                option(
                    f"use_member:{record.member}",
                    f"Use {member.label} ({record.address})",
                    reason=oc.update_reason(record.member),
                )
            )
        else:
            reason = NEEDS_NAMES if not oc.has_names else ""
            if owned_by_member:
                reason = "Another record of this address belongs to a member; merge the duplicates first"
            options.append(
                option(
                    f"create_claim:{record.id}",
                    f"Claim the unlinked record {record.address} for a new member",
                    reason=reason,
                )
            )
    return [*options, skip_option()]


def _mismatch(facts, oc):
    by_uuid, by_email = oc.member(facts["uuid_member"]), oc.member(facts["email_member"])
    return [
        option(
            f"use_member:{by_uuid.id}",
            f"Use {by_uuid.label} (by Member UUID); don't give them the address",
            reason=oc.update_reason(by_uuid.id),
        ),
        option(f"use_member:{by_email.id}", f"Use {by_email.label} (by email)", reason=oc.update_reason(by_email.id)),
        skip_option(),
    ]


def _uuid_not_found(facts, oc):
    text = facts.get("fallback_text")
    reason = (
        "" if facts.get("fallback") else facts.get("fallback_reason") or "Matched by email, this row would be skipped"
    )
    return [
        option(
            "ignore_uuid",
            "Ignore the Member UUID and match by email",
            reason=reason,
            hint=f"The row would {text}" if text else "",
        ),
        skip_option(),
    ]


def _name_differs(facts, oc):
    member = oc.member(facts["target"])
    reason = oc.update_reason(member.id)
    return [
        option("update_same_person", f"Same person: update {member.label}, including the name", reason=reason),
        option("update_keep_name", f"Same person: update {member.label}, keep their name", reason=reason),
        skip_option("Not the same person, or not sure. The address stays with the member."),
    ]


def _address_not_primary(facts, oc):
    member = oc.member(facts["target"])
    record = next(c for c in oc.snapshot.email_records(oc.values.get("primary_email")) if c.member == member.id)
    reason = oc.update_reason(member.id)
    unverified = (
        "Not verified. The member can verify it on /account, or an admin can mark it verified in Contact Emails first."
    )
    primary = member.primary
    return [
        option(
            "update",
            f"Update {member.label}; keep the email roles",
            reason=reason,
            hint=f"The flag cells apply to {record.address}; the primary {primary.address if primary else ''} is kept.",
            suggested=True,
        ),
        option(
            "update_make_primary",
            f"Update {member.label} and make {record.address} their primary",
            reason=reason or ("" if record.verified else unverified),
            hint="The previous primary becomes secondary; nothing is deleted.",
        ),
        skip_option(),
    ]


def _unlinked(facts, oc):
    address = oc.values.get("primary_email")
    reason = NEEDS_NAMES if not oc.has_names else ""
    if facts.get("uuid_member"):
        reason = "The row's Member UUID names an existing member"
    options = [
        option(
            f"create_claim:{facts['record']}",
            f"Create a new member and attach {address} as their primary",
            reason=reason,
            suggested=not reason,
        )
    ]
    for member_id in facts.get("attach_candidates", []):
        member = oc.member(member_id)
        role = "other" if member.emails_of_type("secondary") else "secondary"
        options.append(
            option(
                f"attach_to:{member_id}",
                f'Attach {address} to {member.label} as "{role}" and update them (their name is kept)',
                reason=oc.update_reason(member_id),
            )
        )
    return [*options, skip_option()]


def _skip_mode(facts, oc):
    member = oc.member(facts["target"])
    return [
        skip_option("The upload said to skip rows that match an existing member."),
        option("update", f"Update {member.label} instead", reason=oc.update_reason(member.id)),
    ]


_BUILDERS = {
    "duplicate_in_sheet": _duplicate,
    "privileged_target": _privileged,
    "ambiguous_address": _ambiguous,
    "uuid_email_mismatch": _mismatch,
    "uuid_not_found": _uuid_not_found,
    "name_differs": _name_differs,
    "address_not_primary": _address_not_primary,
    "unlinked_address": _unlinked,
    "exists_but_skip_mode": _skip_mode,
}


def ready_options(status: str, target_label: str = "") -> list[dict]:
    """A ready row's choices: apply it (the default) or skip it with its own tick."""
    if status == "ready_create":
        return [option("create", "Create this member"), skip_option()]
    return [option("update", f"Update {target_label}" if target_label else "Update the member"), skip_option()]


def allowed_values(options: list[dict]) -> set[str]:
    return {item["value"] for item in options if item["enabled"]}


def bulk_value_for(bulk: str, options: list[dict]) -> str | None:
    """The row option a bulk choice stands for, when it is allowed on that row (``create_claim`` matches its id)."""
    for item in options:
        if not item["enabled"]:
            continue
        if item["value"] == bulk or (bulk == "create_claim" and item["value"].startswith("create_claim:")):
            return item["value"]
    return None


def names_match(values: dict, member) -> bool:
    return names_agree(values.get("first_name"), values.get("last_name"), member.first_name, member.last_name)
