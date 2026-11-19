"""Which action a staff member may take on a bounced address right now, and why not.

Seeing the page needs the Mail app. Anything that changes a contact email or a member also needs the Members
(``authn``) app and ``user_can_manage_member`` for every member involved: only an I2G Master may change a staff or
superuser account. Deleting an account is for an I2G Master only: the hard delete also removes the member's records
in apps the admin may not hold (event registrations, check-ins, assistant chats, admin history), which no other admin
path deletes today. Each guard reads the address,
its contact emails and the member live (``load_target``); ``fingerprint`` summarises what they read, so applying an
action refuses when anything changed after the confirmation page was shown.

When the address is a member's primary or only address (plan §3.4):

- deleting the primary needs another **verified** address, which the admin picks as the new primary;
- the member's only email address, and the last verified sign-in contact (email or phone), cannot be deleted;
- an ambiguous address (one address under several letter cases) allows no contact or member change.
"""

from apps.core.utils.access import user_can_access_app, user_can_manage_member

from ..policies.graph import row_has_graph_hold
from .targets import (
    ALLOWED,
    MASTER_DELETES,
    NEEDS_AUTHN,
    PRIVILEGED,
    Action,
    Availability,
    Role,
    Status,
    Target,
    _first_refusal,
    _is_self,
    _member_change,
    _member_role,
    delete_email_blocker,
    member_admin,
    refused,
)


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
    return _member_change(request, target.owners)


def _clear(request, target):
    row = target.row
    if not (row.is_suppressed or row_has_graph_hold(row) or row.legacy_graph_permanent_review):
        return refused("The address has no staff or reviewed Graph hold to clear.")
    return _member_change(request, target.owners) if target.owners else ALLOWED


def _unsubscribe(request, target):
    return _first_refusal(
        lambda: _member_role(target),
        lambda: ALLOWED if target.contact.subscribe else refused("The address is already unsubscribed."),
        lambda: _member_change(request, [target.member]),
    )


def _make_primary(request, target):
    return _first_refusal(
        lambda: ALLOWED if target.role == Role.PRIMARY else refused("Only for the member's primary address."),
        lambda: ALLOWED if target.other_verified() else refused("The member has no other verified address."),
        lambda: _member_change(request, [target.member]),
    )


def _replace(request, target):
    return _first_refusal(lambda: _member_role(target), lambda: _member_change(request, [target.member]))


def _delete_email(request, target):
    if target.role == Role.UNLINKED:
        if not user_can_access_app(request.user, "authn"):
            return refused(NEEDS_AUTHN)
        if not user_can_manage_member(request.user, None):
            return refused("Only an I2G Master may delete a contact email that belongs to no member.")
        return ALLOWED
    return _first_refusal(
        lambda: _member_role(target),
        lambda: _member_change(request, [target.member]),
        lambda: refused(blocker) if (blocker := delete_email_blocker(target)) else ALLOWED,
    )


def _deactivate(request, target):
    return _first_refusal(
        lambda: _member_role(target),
        lambda: ALLOWED if target.member.is_active else refused("The account is already inactive."),
        lambda: refused("You cannot deactivate your own account.") if _is_self(request, target) else ALLOWED,
        lambda: _member_change(request, [target.member]),
    )


def _delete_account(request, target):
    return _first_refusal(
        lambda: _member_role(target),
        lambda: refused("You cannot delete your own account.") if _is_self(request, target) else ALLOWED,
        lambda: ALLOWED if request.user.is_superuser else refused(MASTER_DELETES),
        lambda: _member_change(request, [target.member]),
        lambda: ALLOWED if member_admin().has_delete_permission(request, target.member) else refused(PRIVILEGED),
    )


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
