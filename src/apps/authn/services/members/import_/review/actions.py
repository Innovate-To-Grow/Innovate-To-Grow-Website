"""What a row's choice does, and the writes it plans.

A choice (``"update"``, ``"use_member:<id>"``, …) resolves to an ``Action``: create a member, create one around an
unlinked address, update a member, or skip. The planner turns an action into a ``RowPlan``: the writes (``Op``) in
the order the apply makes them, a line for each change, and notes for what the row asked for but does not get.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

SKIP = "skip"
CREATE = "create"
CREATE_CLAIM = "create_claim"
UPDATE = "update"


@dataclass(frozen=True)
class Action:
    kind: str
    target: str | None = None
    keep_name: bool = False
    make_primary: bool = False
    # The unlinked ContactEmail the action takes: the new member's primary (create_claim), or the address attached
    # to the target (update).
    claim: str | None = None

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "target": self.target,
            "keep_name": self.keep_name,
            "make_primary": self.make_primary,
            "claim": self.claim,
        }


SKIP_ACTION = Action(SKIP)


@dataclass
class Op:
    """One write. ``ref`` is the contact or member it acts on; ``data`` what it sets."""

    kind: str
    ref: str | None = None
    data: dict = field(default_factory=dict)


@dataclass
class RowPlan:
    kind: str
    target: str | None = None
    ops: list[Op] = field(default_factory=list)
    changes: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    # What the confirm and result pages spell out, by kind: "emails_deleted", "phones_deleted", "resubscribed",
    # "unverified", "primary_changes", "active_changes", "staff_changes".
    listed: dict = field(default_factory=lambda: defaultdict(list))

    @property
    def writes(self) -> bool:
        return bool(self.ops)

    def add(self, op: Op, change: str) -> None:
        self.ops.append(op)
        self.changes.append(change)


def resolve_action(choice: str, analysis: dict) -> Action:
    """The action ``choice`` stands for on a row whose analysis is ``analysis`` (see ``analysis.RowAnalysis``)."""
    target = analysis.get("target")
    if not choice or choice == SKIP:
        return SKIP_ACTION
    simple = {
        CREATE: Action(CREATE),
        UPDATE: Action(UPDATE, target=target),
        "update_same_person": Action(UPDATE, target=target),
        "update_keep_name": Action(UPDATE, target=target, keep_name=True),
        "update_make_primary": Action(UPDATE, target=target, make_primary=True),
    }
    if choice in simple:
        return simple[choice]
    if choice in ("use_row", "ignore_uuid"):
        stored = analysis.get("solo" if choice == "use_row" else "fallback")
        return Action(**stored) if stored else SKIP_ACTION
    name, _, ref = choice.partition(":")
    if name == "use_member":
        return Action(UPDATE, target=ref)
    if name == CREATE_CLAIM:
        return Action(CREATE_CLAIM, claim=ref)
    if name == "attach_to":
        # Attaching never renames the member: the row was matched through another cell, not by its name.
        return Action(UPDATE, target=ref, keep_name=True, claim=analysis.get("record"))
    return SKIP_ACTION
