"""Which action an Admin may take on a bounced address right now, and why not.

Every Admin may take every action; what a guard refuses depends only on the address, its contact emails and the
member. Deactivating or deleting an account also applies the Admin lockout rules (``admin_removal_refusal``): nobody
removes their own Admin account, and the last active Admin is never removed. Each guard reads the address, its contact
emails and the member live (``load_target``); ``fingerprint`` summarises what they read, so applying an action refuses
when anything changed after the confirmation page was shown.

When the address is a member's primary or only address (plan §3.4):

- deleting the primary needs another **verified** address, which the admin picks as the new primary;
- the member's only email address, and the last verified sign-in contact (email or phone), cannot be deleted;
- an ambiguous address (one address under several letter cases) allows no contact or member change.
"""

from apps.authn.services.members.admins import DEACTIVATE, DELETE, admin_removal_refusal

from ..policies.graph import row_has_graph_hold
from .targets import (
    ALLOWED,
    Action,
    Availability,
    Role,
    Status,
    Target,
    _first_refusal,
    _member_role,
    delete_email_blocker,
    member_admin,
    refused,
)

DELETE_REFUSED = "The Members admin does not allow deleting this account."


def _dismiss(request, target):
    return ALLOWED if target.row.status == Status.OPEN else refused("Only an open address can be dismissed.")


def _reopen(request, target):
    return refused("The address is already open.") if target.row.status == Status.OPEN else ALLOWED


def _suppress(request, target):
    if target.row.is_suppressed:
        return refused("The address is already suppressed.")
    if target.role not in (Role.NONE, Role.UNLINKED):
        return refused("The address is a member's contact email: use Mark undeliverable.")
    return ALLOWED


def _mark_undeliverable(request, target):
    if target.row.is_suppressed:
        return refused("The address is already marked undeliverable.")
    if target.role in (Role.NONE, Role.UNLINKED):
        return refused("The address is not a member's contact email: use Suppress address.")
    return ALLOWED


def _clear(request, target):
    row = target.row
    if not (row.is_suppressed or row_has_graph_hold(row) or row.legacy_graph_permanent_review):
        return refused("The address has no staff or reviewed Graph hold to clear.")
    return ALLOWED


def _unsubscribe(request, target):
    return _first_refusal(
        lambda: _member_role(target),
        lambda: ALLOWED if target.contact.subscribe else refused("The address is already unsubscribed."),
    )


def _make_primary(request, target):
    return _first_refusal(
        lambda: ALLOWED if target.role == Role.PRIMARY else refused("Only for the member's primary address."),
        lambda: ALLOWED if target.other_verified() else refused("The member has no other verified address."),
    )


def _replace(request, target):
    return _member_role(target)


def _delete_email(request, target):
    if target.role == Role.UNLINKED:
        return ALLOWED
    return _first_refusal(
        lambda: _member_role(target),
        lambda: refused(blocker) if (blocker := delete_email_blocker(target)) else ALLOWED,
    )


def _deactivate(request, target):
    return _first_refusal(
        lambda: _member_role(target),
        lambda: ALLOWED if target.member.is_active else refused("The account is already inactive."),
        lambda: _lockout(request, target, DEACTIVATE),
    )


def _delete_account(request, target):
    return _first_refusal(
        lambda: _member_role(target),
        lambda: _lockout(request, target, DELETE),
        lambda: ALLOWED if member_admin().has_delete_permission(request, target.member) else refused(DELETE_REFUSED),
    )


def _lockout(request, target, action: str) -> Availability:
    """The Admin lockout rules: never the actor's own Admin account, never the last active Admin."""
    reason = admin_removal_refusal(request.user, [target.member], action=action)
    return refused(reason) if reason else ALLOWED


GUARDS = {
    Action.DISMISS: _dismiss,
    Action.REOPEN: _reopen,
    Action.SUPPRESS: _suppress,
    Action.MARK_UNDELIVERABLE: _mark_undeliverable,
    Action.CLEAR_SUPPRESSION: _clear,
    Action.UNSUBSCRIBE: _unsubscribe,
    Action.MAKE_PRIMARY: _make_primary,
    Action.REPLACE: _replace,
    Action.DELETE_EMAIL: _delete_email,
    Action.DEACTIVATE: _deactivate,
    Action.DELETE_ACCOUNT: _delete_account,
}


def availability(action: str, request, target: Target) -> Availability:
    guard = GUARDS.get(action)
    return guard(request, target) if guard is not None else refused("Unknown action.")
