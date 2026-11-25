"""Plan exactly what one row writes for the action chosen for it.

The same plan is shown under the selected choice on the review page, counted on the confirm page, and carried out by
the apply, which re-plans from freshly read records (the fingerprint check makes sure they are the ones reviewed).

An update writes, in this order: the profile fields the row changes; the Primary Email cell's flags (on that address
only, and only when the member owns it); a promotion, when chosen; the Secondary Email cell; the Phone Number cell;
the Active cell, when ticked (the Admin or Staff column is never read); and last, the ticked removals. A new member is created as before: the
sheet's flags are trusted for a brand-new member's own email addresses. Its phone number is always saved unverified:
the Phone Verified column is ignored, because only the member's own one-time code may verify a number.
"""

from __future__ import annotations

from ..lookup.records import Snapshot
from .actions import SKIP, UPDATE, Action, RowPlan
from .creates import _plan_create
from .updates import _plan_update


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
