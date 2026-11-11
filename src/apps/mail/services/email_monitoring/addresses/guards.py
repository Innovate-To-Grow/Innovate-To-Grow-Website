"""Which action a staff member may take on a bounced address right now, and why not.

Seeing the page needs the Mail app. Anything that changes a contact email or a member also needs the Members
(``authn``) app and ``user_can_manage_member`` for every member involved: only an I2G Master may change a staff or
superuser account. Deleting an account needs the Member admin's own delete permission. Each guard reads the address,
its contact emails and the member live (``load_target``); ``fingerprint`` summarises what they read, so applying an
action refuses when anything changed after the confirmation page was shown.

When the address is a member's primary or only address (plan §3.4):

- deleting the primary needs another **verified** address, which the admin picks as the new primary;
- the member's only email address, and the last verified sign-in contact (email or phone), cannot be deleted;
- an ambiguous address (one address under several letter cases) allows no contact or member change.
"""

import hashlib
import json
from dataclasses import dataclass, field

from django.contrib import admin
from django.contrib.auth import get_user_model

from apps.authn.models import ContactEmail
from apps.authn.services.account.recovery import count_verified_recovery_contacts
from apps.core.utils.access import user_can_access_app, user_can_manage_member
from apps.mail.models import BouncedAddress, BouncedAddressAction

from .matching import MEMBER_ROLES, AddressMatch, match_address

Action = BouncedAddressAction.Action
Role = BouncedAddress.Role
Status = BouncedAddress.Status

NEEDS_AUTHN = "Needs the Members (authn) app as well as Mail."
PRIVILEGED = "Only an I2G Master may change a staff or superuser account."
ROLE_REASONS = {
    Role.NONE: "The address belongs to no contact email.",
    Role.UNLINKED: "The contact email belongs to no member.",
    Role.AMBIGUOUS: (
        "The address is saved under several letter cases; resolve the duplicates in Contact Emails first."
    ),
}


@dataclass(frozen=True)
class Availability:
    allowed: bool
    reason: str = ""


ALLOWED = Availability(True)


def refused(reason: str) -> Availability:
    return Availability(False, reason)


@dataclass
class Target:
    """An address as it stands now: its row, its contact emails, and the one member it belongs to (if any)."""

    row: BouncedAddress
    match: AddressMatch
    member_contacts: list = field(default_factory=list)
    verified_phones: int = 0

    @property
    def role(self) -> str:
        return self.match.role

    @property
    def contact(self):
        return self.match.contact

    @property
    def member(self):
        return self.match.member if self.role in MEMBER_ROLES else None

    @property
    def owners(self) -> list:
        return self.match.owners

    def other_verified(self) -> list:
        """The member's other verified contact emails (candidates for primary)."""
        contact = self.contact
        return [item for item in self.member_contacts if item.verified and (contact is None or item.pk != contact.pk)]


def load_target(row: BouncedAddress, *, lock: bool = False) -> Target:
    """Read the address's live state; ``lock`` locks the member row first (the mutex authn's services use)."""
    match = match_address(row.address)
    member = match.member if match.role in MEMBER_ROLES else None
    if lock and member is not None:
        get_user_model().objects.select_for_update().filter(pk=member.pk).first()
        match = match_address(row.address)
        member = match.member if match.role in MEMBER_ROLES else None
    contacts = list(ContactEmail.objects.filter(member=member).order_by("created_at", "pk")) if member else []
    phones = member.contact_phones.filter(verified=True).count() if member else 0
    return Target(row=row, match=match, member_contacts=contacts, verified_phones=phones)


def fingerprint(target: Target) -> str:
    """A digest of everything the guards read (not the counts: a new report does not invalidate a confirmation)."""
    row = target.row
    member = target.member
    parts = [
        row.address,
        row.status,
        row.suppression,
        row.suppressed_at.isoformat() if row.suppressed_at else "",
        [(c.pk, c.email_address, c.email_type, c.verified, c.subscribe, c.member_id) for c in target.match.contacts],
        [(m.pk, m.is_active, m.is_staff, m.is_superuser) for m in target.owners],
        [(c.pk, c.email_address, c.email_type, c.verified, c.subscribe) for c in target.member_contacts],
        target.verified_phones,
        member.pk if member is not None else None,
    ]
    return hashlib.sha256(json.dumps(parts, default=str).encode("utf-8")).hexdigest()[:40]


def _member_change(request, members) -> Availability:
    if not user_can_access_app(request.user, "authn"):
        return refused(NEEDS_AUTHN)
    if any(not user_can_manage_member(request.user, member) for member in members):
        return refused(PRIVILEGED)
    return ALLOWED


def _member_role(target: Target) -> Availability:
    return ALLOWED if target.role in MEMBER_ROLES else refused(ROLE_REASONS[target.role])


def _first_refusal(*checks) -> Availability:
    for check in checks:
        result = check()
        if not result.allowed:
            return result
    return ALLOWED


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
    if not target.row.is_suppressed:
        return refused("The address is not suppressed.")
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


def delete_email_blocker(target: Target) -> str:
    """Why the member's contact email cannot be deleted (plan §3.4), or ""."""
    contact = target.contact
    if len(target.member_contacts) <= 1:
        return "This is the member's only email address: deactivate or delete the account instead."
    if target.role == Role.PRIMARY and not target.other_verified():
        return (
            "This is the primary address and the member has no other verified address: replace it, mark it "
            "undeliverable, or deactivate the account."
        )
    if contact.verified and count_verified_recovery_contacts(target.member, exclude_email_pk=contact.pk) == 0:
        return "This is the member's last verified sign-in contact (email or phone)."
    return ""


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
        lambda: _member_change(request, [target.member]),
        lambda: ALLOWED if member_admin().has_delete_permission(request, target.member) else refused(PRIVILEGED),
    )


def _is_self(request, target) -> bool:
    return target.member is not None and target.member.pk == request.user.pk


def member_admin():
    return admin.site.get_model_admin(get_user_model())


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
