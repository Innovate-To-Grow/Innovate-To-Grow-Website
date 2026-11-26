"""The profile fields an import writes, their labels, and the notes a plan attaches to a row."""

from __future__ import annotations

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
PENDING_NOTE = (
    "The member's self-service sign-up is unfinished; an import never activates it or verifies its contacts (only "
    "the person can, by confirming their email)"
)
