"""What the action handlers share: their refusals, and the review and suppression fields they set on the row."""

from django.utils import timezone

from apps.authn.models import ContactEmail
from apps.mail.models import BouncedAddress

from . import audit
from .suggestions import suggest

REVIEW_FIELDS = ["status", "resolution", "reviewed_by", "reviewed_at", "review_note"]
SUPPRESSION_FIELDS = ["suppression", "suppressed_at", "suppressed_by", "suppressed_reason"]


class ActionRefused(Exception):
    """The action may not be applied now (a guard, a typed confirmation or an input); nothing changed."""


class StaleConfirmation(Exception):
    """The address, its contact emails or its member changed since the confirmation page was shown."""


def note_of(values: dict) -> str:
    return str(values.get("note") or "").strip()[:500]


def review(request, row: BouncedAddress, status: str, resolution: str, note: str) -> None:
    row.status = status
    row.resolution = resolution
    row.reviewed_by = request.user
    row.reviewed_at = timezone.now()
    row.review_note = (note or "")[:500]


def suppress(request, row: BouncedAddress, kind: str, reason: str) -> None:
    row.suppression = kind
    row.suppressed_at = timezone.now()
    row.suppressed_by = request.user
    row.suppressed_reason = (reason or audit.evidence(row))[:500]


def save(row: BouncedAddress, fields) -> None:
    row.suggestion = suggest(row)
    row.save(update_fields=[*fields, "suggestion", "updated_at"])


def history_targets(target) -> list:
    """Where the admin history line goes: every member holding the address, or the bounced-address row."""
    return target.owners or [target.row]


def verified_choice(target, value) -> ContactEmail:
    """The member's other verified address the admin picked (by primary key)."""
    chosen = next((item for item in target.other_verified() if str(item.pk) == str(value or "")), None)
    if chosen is None:
        raise ActionRefused("Pick one of the member's other verified addresses as the new primary.")
    return chosen
