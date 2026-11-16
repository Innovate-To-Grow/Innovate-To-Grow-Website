"""What each staff action does to a bounced address (queue state, contact emails, accounts)."""

from django.contrib.admin.models import DELETION

from apps.authn.models import ContactEmail
from apps.authn.services.account import delete_member_account
from apps.authn.services.contacts.contact_emails import delete_contact_email, make_contact_email_primary
from apps.authn.services.email.challenges import AuthChallengeError
from apps.mail.models import BouncedAddress, BouncedAddressAction

from . import audit, effects
from .effects import ActionRefused
from .targets import Target, member_admin

Action = BouncedAddressAction.Action
Role = BouncedAddress.Role
Status = BouncedAddress.Status
Suppression = BouncedAddress.Suppression


# --- Queue state and suppression --------------------------------------------------------------------------------------


def _dismiss(request, target: Target, values: dict) -> str:
    note = effects.note_of(values)
    if not note:
        raise ActionRefused("Give a reason for dismissing the address.")
    effects.review(request, target.row, Status.DISMISSED, Action.DISMISS, note)
    effects.save(target.row, effects.REVIEW_FIELDS)
    audit.record(request, target, Action.DISMISS, note=note, role_after=target.role)
    audit.history(request, [target.row], f"dismissed {target.row.address} ({audit.evidence(target.row)}): {note}")
    return f"{target.row.address} was dismissed."


def _reopen(request, target: Target, values: dict) -> str:
    note = effects.note_of(values)
    effects.review(request, target.row, Status.OPEN, "", note)
    effects.save(target.row, effects.REVIEW_FIELDS)
    audit.record(request, target, Action.REOPEN, note=note, role_after=target.role)
    audit.history(request, [target.row], f"reopened {target.row.address}")
    return f"{target.row.address} is open again."


def _suppressor(kind: str, action: str, verb: str):
    def apply(request, target: Target, values: dict) -> str:
        note = effects.note_of(values)
        effects.suppress(request, target.row, kind, note)
        effects.review(request, target.row, Status.RESOLVED, action, note)
        effects.save(target.row, [*effects.SUPPRESSION_FIELDS, *effects.REVIEW_FIELDS])
        audit.record(request, target, action, note=note, role_after=target.role)
        message = f"{verb} {target.row.address} ({audit.evidence(target.row)})"
        audit.history(request, effects.history_targets(target), message)
        return f"{target.row.address} is {verb}: campaigns skip it from now on."

    return apply


def _clear(request, target: Target, values: dict) -> str:
    note = effects.note_of(values)
    row = target.row
    previous = row.get_suppression_display() or "suppressed"
    row.suppression, row.suppressed_at, row.suppressed_by, row.suppressed_reason = "", None, None, ""
    effects.review(request, row, Status.OPEN, "", note)
    effects.save(row, [*effects.SUPPRESSION_FIELDS, *effects.REVIEW_FIELDS])
    audit.record(request, target, Action.CLEAR_SUPPRESSION, note=note, role_after=target.role)
    audit.history(request, effects.history_targets(target), f"cleared “{previous}” on {row.address}")
    return f"{row.address} is no longer suppressed: campaigns may mail it again."


def _unsubscribe(request, target: Target, values: dict) -> str:
    note = effects.note_of(values)
    contact = target.contact
    contact.subscribe = False
    contact.save(update_fields=["subscribe", "updated_at"])  # a save, so the member sheet sync sees it
    effects.review(request, target.row, Status.RESOLVED, Action.UNSUBSCRIBE, note)
    effects.save(target.row, effects.REVIEW_FIELDS)
    audit.record(request, target, Action.UNSUBSCRIBE, note=note, role_after=target.role)
    audit.history(request, [target.member], f"unsubscribed {target.row.address} ({audit.evidence(target.row)})")
    return f"{target.row.address} is unsubscribed from newsletters."


# --- Contact emails ---------------------------------------------------------------------------------------------------


def _make_primary(request, target: Target, values: dict) -> str:
    chosen = effects.verified_choice(target, values.get("new_primary"))
    note = effects.note_of(values)
    try:
        make_contact_email_primary(member=target.member, contact_email_id=chosen.pk)
    except AuthChallengeError as exc:
        raise ActionRefused(str(exc)) from exc
    effects.review(request, target.row, Status.RESOLVED, Action.MAKE_PRIMARY, note)
    effects.save(target.row, effects.REVIEW_FIELDS)
    details = {"new_primary": chosen.email_address}
    audit.record(request, target, Action.MAKE_PRIMARY, note=note, role_after=Role.SECONDARY, details=details)
    message = f"made {chosen.email_address} the primary email instead of {target.row.address}"
    audit.history(request, [target.member], f"{message} ({audit.evidence(target.row)})")
    return f"{chosen.email_address} is now the primary address; {target.row.address} is the secondary."


def _remove_contact(target: Target, values: dict) -> None:
    """Delete the bounced contact email (the guards and the primary-address rules already passed)."""
    if target.role == Role.UNLINKED:
        deleted, _counts = ContactEmail.objects.filter(pk=target.contact.pk, member__isnull=True).delete()
        if not deleted:
            raise ActionRefused("The contact email changed meanwhile; reload the page and try again.")
        return
    try:
        if target.role == Role.PRIMARY:
            chosen = effects.verified_choice(target, values.get("new_primary"))
            make_contact_email_primary(member=target.member, contact_email_id=chosen.pk)
        delete_contact_email(member=target.member, contact_email_id=target.contact.pk)
    except AuthChallengeError as exc:
        raise ActionRefused(str(exc)) from exc


def _delete_email(request, target: Target, values: dict) -> str:
    note = effects.note_of(values)
    address = target.contact.email_address
    details = {}
    if target.role == Role.PRIMARY:
        details["new_primary"] = effects.verified_choice(target, values.get("new_primary")).email_address
    message = f"deleted the contact email {address} ({audit.evidence(target.row)})"
    audit.history(request, effects.history_targets(target), message)
    audit.record(request, target, Action.DELETE_EMAIL, note=note, role_after=Role.NONE, details=details)
    _remove_contact(target, values)
    effects.review(request, target.row, Status.RESOLVED, Action.DELETE_EMAIL, note)
    effects.save(target.row, effects.REVIEW_FIELDS)
    return f"The contact email {address} was deleted."


# --- Accounts ---------------------------------------------------------------------------------------------------------


def _deactivate(request, target: Target, values: dict) -> str:
    note = effects.note_of(values)
    member = target.member
    # As the Member admin's deactivate action: an unfinished self-service sign-up ends too. A save, not an update,
    # so the member sheet sync sees it.
    member.is_active = False
    member.registration_pending = False
    member.save(update_fields=["is_active", "registration_pending", "updated_at"])
    effects.review(request, target.row, Status.RESOLVED, Action.DEACTIVATE, note)
    effects.save(target.row, effects.REVIEW_FIELDS)
    audit.record(request, target, Action.DEACTIVATE, note=note, role_after=target.role)
    audit.history(request, [member], f"deactivated the account ({target.row.address}: {audit.evidence(target.row)})")
    return f"{audit.person_label(member)} was deactivated."


def deletion_summary(request, member) -> dict:
    """What deleting ``member`` removes, as the stock delete page lists it (``get_deleted_objects``)."""
    deleted, model_count, _perms_needed, protected = member_admin().get_deleted_objects([member], request)
    return {"deleted": deleted, "model_count": sorted(model_count.items()), "protected": list(protected)}


def _delete_account(request, target: Target, values: dict) -> str:
    note = effects.note_of(values)
    member = target.member
    label = audit.person_label(member)
    if deletion_summary(request, member)["protected"]:
        raise ActionRefused("Other records protect this account from deletion; deactivate it instead.")
    message = f"deleted the account ({target.row.address}: {audit.evidence(target.row)})"
    audit.history(request, [member], message, flag=DELETION)
    audit.record(request, target, Action.DELETE_ACCOUNT, note=note, role_after=Role.NONE, details={"member": label})
    delete_member_account(member=member)
    effects.review(request, target.row, Status.RESOLVED, Action.DELETE_ACCOUNT, note)
    effects.save(target.row, effects.REVIEW_FIELDS)
    return f"The account of {label} was deleted."
