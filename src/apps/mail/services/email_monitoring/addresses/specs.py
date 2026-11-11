"""What each bounced-address action does, whether it can be undone, and how it is confirmed (shown on the address
page and the confirmation page)."""

from dataclasses import dataclass

from django.conf import settings

from apps.mail.models import BouncedAddressAction

Action = BouncedAddressAction.Action


@dataclass(frozen=True)
class Spec:
    label: str
    effect: str
    reversible: str
    # "address": type the address; "primary": type the member's primary address. Only while
    # ADMIN_REQUIRE_CONFIRMATION is on (like the other admin flows). Replace email asks for the old address only
    # when it deletes it.
    typed: str = ""
    # Offered in the list's row menu and as a bulk action (the reversible, address-level actions).
    quick: bool = False
    danger: bool = False


SPECS = {
    Action.DISMISS: Spec(
        "Dismiss", "The address leaves the open queue. Nothing else changes.", "Yes: Reopen.", quick=True
    ),
    Action.REOPEN: Spec("Reopen", "The address goes back to the open queue.", "Yes: Dismiss.", quick=True),
    Action.SUPPRESS: Spec(
        "Suppress address",
        "Every campaign audience skips this address (it belongs to no member), including queued sends that have not "
        "gone out yet. Sign-in codes and tickets still go.",
        "Yes: Clear suppression.",
        quick=True,
    ),
    Action.MARK_UNDELIVERABLE: Spec(
        "Mark undeliverable",
        "Every campaign audience skips this address, including queued sends that have not gone out yet. Sign-in "
        "codes, tickets and notifications still go: the person may fix their mailbox.",
        "Yes: Clear suppression.",
        quick=True,
    ),
    Action.CLEAR_SUPPRESSION: Spec(
        "Clear suppression", "Campaigns may mail the address again.", "Yes: suppress it again.", quick=True
    ),
    Action.UNSUBSCRIBE: Spec(
        "Unsubscribe this address",
        "Turns off newsletters (the All subscribers audience) for this address only; the member's other addresses "
        "keep their own setting.",
        "Yes: re-subscribe the address on the member's page.",
        quick=True,
    ),
    Action.MAKE_PRIMARY: Spec(
        "Use another address as primary",
        "The verified address you pick becomes the primary; this address becomes the secondary, and the previous "
        "secondary becomes other.",
        "Yes: make this address primary again once it is verified.",
    ),
    Action.REPLACE: Spec(
        "Replace email",
        "Adds the new address to the member, then marks this address undeliverable or deletes it. Nothing is sent to "
        "the new address: the member can verify it from their account page.",
        "Partly: the new address can be removed again; a deleted old address cannot be restored.",
    ),
    Action.DELETE_EMAIL: Spec(
        "Delete this email address",
        "Removes this contact email (the member's other addresses stay).",
        "No.",
        typed="address",
        danger=True,
    ),
    Action.DEACTIVATE: Spec(
        "Deactivate account",
        "The member can no longer sign in, and inactive members are left out of every member audience. Their "
        "registrations, check-ins and history stay. An unfinished self-service sign-up ends.",
        "Yes: activate the member again on the Members page.",
        danger=True,
    ),
    Action.DELETE_ACCOUNT: Spec(
        "Delete account",
        "Permanently deletes the member and everything that belongs to them (listed on the confirmation page).",
        "No.",
        typed="primary",
        danger=True,
    ),
}
QUICK_ACTIONS = tuple(action for action, spec in SPECS.items() if spec.quick)


def confirmation_required() -> bool:
    """Typed confirmations follow ``ADMIN_REQUIRE_CONFIRMATION`` (on unless a settings module turns it off)."""
    return bool(getattr(settings, "ADMIN_REQUIRE_CONFIRMATION", True))


def confirmation_text(action: str, target) -> str:
    """What the admin types to confirm ``action`` on ``target`` ("" when it takes no typed confirmation)."""
    typed = SPECS[action].typed
    if typed == "address":
        return target.contact.email_address if target.contact is not None else target.row.address
    if typed == "primary":
        member = target.member
        return (member.get_primary_email() if member is not None else "") or target.row.address
    return ""
