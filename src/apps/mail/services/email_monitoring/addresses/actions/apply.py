"""Applying one staff action to one bounced address.

Every action is explicit: a POST from the address page (or the list) to a confirmation page, then an "apply" POST.
``apply_action`` takes the row and the member locks, re-reads the address, its contact emails and the member, and
refuses (``StaleConfirmation``) when anything the guards read changed since the confirmation page was shown, or
(``ActionRefused``) when the guard, a typed confirmation or an input says no. Nothing is changed in either case. An
applied action leaves a ``BouncedAddressAction`` row and an admin history line (``audit``).

The contact and account changes reuse the Members app's own services and their invariants:
``make_contact_email_primary`` (only a verified address becomes primary), ``delete_contact_email`` (never the last
verified sign-in contact) and ``delete_member_account`` (a hard delete that cascades, so Deactivate is offered first).
"""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.mail.models import BouncedAddress

from ..listing.matching import refresh_cached_links
from .effects import ActionRefused, StaleConfirmation
from .guards import availability
from .handlers import (
    Action,
    Suppression,
    _clear,
    _deactivate,
    _delete_account,
    _delete_email,
    _dismiss,
    _make_primary,
    _reopen,
    _suppressor,
    _unsubscribe,
)
from .replace import apply_replace
from .specs import confirmation_required, confirmation_text
from .targets import Target, fingerprint, load_target

APPLY = {
    Action.DISMISS: _dismiss,
    Action.REOPEN: _reopen,
    Action.SUPPRESS: _suppressor(Suppression.SUPPRESSED, Action.SUPPRESS, "suppressed"),
    Action.MARK_UNDELIVERABLE: _suppressor(
        Suppression.UNDELIVERABLE, Action.MARK_UNDELIVERABLE, "marked undeliverable"
    ),
    Action.CLEAR_SUPPRESSION: _clear,
    Action.UNSUBSCRIBE: _unsubscribe,
    Action.MAKE_PRIMARY: _make_primary,
    Action.REPLACE: apply_replace,
    Action.DELETE_EMAIL: _delete_email,
    Action.DEACTIVATE: _deactivate,
    Action.DELETE_ACCOUNT: _delete_account,
}


def _check_typed(action: str, target: Target, values: dict) -> None:
    expected = confirmation_text(action, target)
    if expected and confirmation_required():
        if str(values.get("confirm") or "").strip().casefold() != expected.casefold():
            raise ActionRefused(f"Type {expected} exactly to confirm.")


def apply_action(request, row_pk, action: str, *, seen: str, values: dict) -> str:
    """Apply ``action`` to the address with primary key ``row_pk``; ``seen`` is the fingerprint the confirmation page
    showed. Returns the success message; raises ``StaleConfirmation`` or ``ActionRefused`` with nothing changed."""
    handler = APPLY.get(action)
    if handler is None:
        raise ActionRefused("Unknown action.")
    with transaction.atomic():
        row = BouncedAddress.objects.select_for_update().get(pk=row_pk)
        target = load_target(row, lock=True)
        if fingerprint(target) != seen:
            raise StaleConfirmation
        verdict = availability(action, request, target)
        if not verdict.allowed:
            raise ActionRefused(verdict.reason)
        _check_typed(action, target, values)
        try:
            message = handler(request, target, values)
        except ValidationError as exc:
            raise ActionRefused(" ".join(exc.messages)) from exc
        except IntegrityError as exc:
            raise ActionRefused("The change conflicts with another record; reload the page and try again.") from exc
        refresh_cached_links([row])
    return message
