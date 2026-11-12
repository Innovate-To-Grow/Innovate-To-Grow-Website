"""Replace email: add a new address to the member, then mark the bounced one undeliverable (the default) or delete it.

- The new address must be a valid address that no contact email holds, in any letter case.
- It is added as secondary (while the member has no other secondary), other, or primary. A primary must be verified:
  the admin attests that the member confirmed it, which is refused on a staff or superuser account unless the admin is
  an I2G Master. The swap goes through ``make_contact_email_primary``: the old primary becomes the secondary.
- Deleting the old address asks for its typed address (with ``ADMIN_REQUIRE_CONFIRMATION``) and goes through
  ``delete_contact_email``, which never removes the last verified sign-in contact. The old primary can only be deleted
  when the new address becomes the primary.
- Nothing is sent: the member can verify the new address from their account page.
"""

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from apps.authn.models import AdminInvitation, ContactEmail
from apps.authn.services.contacts.contact_emails import delete_contact_email, make_contact_email_primary
from apps.authn.services.email.challenges import AuthChallengeError
from apps.mail.models import BouncedAddress, BouncedAddressAction
from apps.mail.services.suppression import normalize_address

from . import audit, effects
from .effects import ActionRefused
from .matching import match_address
from .specs import confirmation_required

Role = BouncedAddress.Role
NEW_ROLES = ("secondary", "other", "primary")
OLD_DISPOSITIONS = ("undeliverable", "delete")


def attest_allowed(request, member) -> bool:
    """Whether the admin may mark a new address verified on ``member``'s account."""
    return bool(request.user.is_superuser or not (member.is_staff or member.is_superuser))


def secondary_taken(target, *, deleting_old: bool) -> bool:
    """Whether another address holds the member's secondary slot (the old one does not count when it is deleted)."""
    old = target.contact
    return any(
        item.email_type == "secondary" and not (deleting_old and item.pk == old.pk) for item in target.member_contacts
    )


def _new_address(target, values) -> str:
    raw = str(values.get("new_address") or "").strip()
    new = normalize_address(raw)
    try:
        validate_email(new)
    except ValidationError as exc:
        raise ActionRefused("Enter a valid new email address.") from exc
    if new == target.row.address:
        raise ActionRefused("The new address is the bounced address itself.")
    if ContactEmail.objects.filter(email_address__iexact=new).exists():
        raise ActionRefused("That address already belongs to a contact email (in some letter case).")
    # Accepting an admin invitation upgrades the member who holds a verified contact email for the invited address,
    # so a pending invitation's address must never be added to another account here.
    if AdminInvitation.objects.filter(email__iexact=new, status=AdminInvitation.Status.PENDING).exists():
        raise ActionRefused("That address has a pending admin invitation; it cannot be added to another account.")
    return new


def _plan(request, target, values) -> dict:
    new = _new_address(target, values)
    role = values.get("new_role") or "secondary"
    if role not in NEW_ROLES:
        raise ActionRefused("Choose primary, secondary or other for the new address.")
    verified = bool(values.get("attest_verified"))
    if verified and not attest_allowed(request, target.member):
        raise ActionRefused("Only an I2G Master may mark an address verified on a staff or superuser account.")
    if role == "primary" and not verified:
        raise ActionRefused("A new primary address must be verified: tick “The member confirmed this address”.")
    delete_old = values.get("old_address") == "delete"
    if delete_old and target.role == Role.PRIMARY and role != "primary":
        raise ActionRefused("To delete the old primary address, make the new address the primary.")
    if role == "secondary" and secondary_taken(target, deleting_old=delete_old):
        raise ActionRefused("The member already has a secondary address: add the new one as Other.")
    if delete_old and confirmation_required():
        old = target.contact.email_address
        if str(values.get("confirm") or "").strip().casefold() != old.casefold():
            raise ActionRefused(f"Type {old} exactly to confirm deleting the old address.")
    return {"new": new, "role": role, "verified": verified, "delete_old": delete_old}


def _swap(target, plan: dict, subscribe: bool) -> None:
    """Add the new address and delete the old one when asked, in an order that keeps every authn invariant."""
    member, old = target.member, target.contact
    wants_slot = plan["role"] == "secondary"
    first_type = (
        "other" if plan["role"] == "primary" or (wants_slot and old.email_type == "secondary") else plan["role"]
    )
    created = ContactEmail(
        member=member, email_address=plan["new"], email_type=first_type, subscribe=subscribe, verified=plan["verified"]
    )
    created.full_clean()
    created.save()
    try:
        if plan["role"] == "primary":
            make_contact_email_primary(member=member, contact_email_id=created.pk)
        if plan["delete_old"]:
            delete_contact_email(member=member, contact_email_id=old.pk)
    except AuthChallengeError as exc:
        raise ActionRefused(str(exc)) from exc
    if wants_slot and created.email_type != "secondary":
        created.email_type = "secondary"
        created.save(update_fields=["email_type", "updated_at"])


def apply_replace(request, target, values: dict) -> str:
    plan = _plan(request, target, values)
    note = effects.note_of(values)
    old = target.contact.email_address
    subscribe = bool(values.get("subscribe"))
    outcome = "deleted" if plan["delete_old"] else "marked undeliverable"
    described = f"new {plan['role']}{', marked verified' if plan['verified'] else ''}; old address {outcome}"
    audit.history(
        request, [target.member], f"replaced {old} with {plan['new']} ({described}) ({audit.evidence(target.row)})"
    )
    _swap(target, plan, subscribe)
    row = target.row
    fields = list(effects.REVIEW_FIELDS)
    if not plan["delete_old"] and not row.is_suppressed:
        effects.suppress(request, row, BouncedAddress.Suppression.UNDELIVERABLE, note or f"Replaced by {plan['new']}.")
        fields += effects.SUPPRESSION_FIELDS
    effects.review(request, row, BouncedAddress.Status.RESOLVED, BouncedAddressAction.Action.REPLACE, note)
    effects.save(row, fields)
    details = {
        "new_address": plan["new"],
        "new_role": plan["role"],
        "verified": plan["verified"],
        "subscribed": subscribe,
        "old_address": outcome,
    }
    role_after = match_address(row.address).role
    audit.record(
        request, target, BouncedAddressAction.Action.REPLACE, note=note, role_after=role_after, details=details
    )
    return f"{plan['new']} was added to {audit.person_label(target.member)}; {old} was {outcome}."
