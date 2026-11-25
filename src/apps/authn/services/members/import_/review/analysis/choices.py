"""The choices a review offers for each row, and which of them a bulk control may set.

Every row that needs a decision starts on "Skip this row": nothing happens to a conflict until an admin picks a choice
for it. The choice the import plan suggests is marked, so it is one click away. A choice that is not allowed stays
visible but disabled, with the reason. The server accepts only a choice from the row's own list (a forged POST fails)
and checks it again at apply.
"""

from __future__ import annotations

from ..lookup.names import names_agree
from ..lookup.records import Snapshot
from ..plan.actions import SKIP

NO_CHANGE_PERMISSION = "You do not have permission to change members"
NEEDS_NAMES = "A new member needs a first and a last name; fill them in the sheet"
# The bulk choices of each conflict: only those an admin may set for a whole group without looking at each row.
BULK_CHOICES = {
    "duplicate_in_sheet": ("use_first", SKIP),
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
        return "" if self.ctx.can_update else NO_CHANGE_PERMISSION

    @property
    def has_names(self) -> bool:
        return bool(self.values.get("first_name") and self.values.get("last_name"))


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
