"""The contact writes an import makes, each guarded, and the checks a sheet's addresses and numbers must pass.

Every write here runs inside the import's one transaction, after the apply has locked the member. A write whose
record is not what the review saw raises ``ContactWriteError``, which rolls the whole import back. The account page's
own services do the promotions and deletions, so their guards hold: an unverified address can't become primary, and a
member's last verified sign-in contact can't be removed.

Nothing here sends mail or SMS: addresses are written directly, never through ``create_contact_email``, which emails a
verification code and a security notice. ``create_contact_phone`` sends nothing and stores numbers unverified.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from apps.authn.models import ContactEmail, ContactPhone
from apps.authn.services.contacts.contact_emails import delete_contact_email, make_contact_email_primary
from apps.authn.services.contacts.contact_phones import (
    create_contact_phone,
    delete_contact_phone,
    infer_region_from_e164,
    normalize_to_national,
)

_EMAIL_MAX_LENGTH = ContactEmail._meta.get_field("email_address").max_length


class ContactWriteError(Exception):
    """A planned contact write found the record changed, or a guard refused it."""


def valid_new_address(address: str) -> bool:
    """Whether ``address`` may be stored as a new contact email (the bulk paths skip model validation)."""
    if len(address) > _EMAIL_MAX_LENGTH:
        return False
    try:
        validate_email(address)
    except ValidationError:
        return False
    return True


def phone_parts(raw: str | None) -> tuple[str, str]:
    """``(national digits, region)`` for a cleaned Phone Number cell; ``("", "")`` when there is none."""
    if not raw:
        return "", ""
    region = infer_region_from_e164(raw)
    return normalize_to_national(raw, region), region


def _owned_email(member, ref: str) -> ContactEmail:
    contact = ContactEmail.objects.select_for_update().filter(pk=ref, member=member).first()
    if contact is None:
        raise ContactWriteError("a contact email the review showed no longer belongs to this member")
    return contact


def set_email_flags(member, ref: str, data: dict) -> None:
    contact = _owned_email(member, ref)
    for name, value in data.items():
        setattr(contact, name, value)
    contact.save(update_fields=[*data, "updated_at"])


def set_phone_flags(member, ref: str, data: dict) -> None:
    phone = ContactPhone.objects.select_for_update().filter(pk=ref, member=member).first()
    if phone is None:
        raise ContactWriteError("a phone number the review showed no longer belongs to this member")
    for name, value in data.items():
        setattr(phone, name, value)
    phone.save(update_fields=[*data, "updated_at"])


def promote_email(member, ref: str) -> None:
    """Make the address primary: the old primary becomes secondary and the old secondary "other"."""
    try:
        make_contact_email_primary(member=member, contact_email_id=ref)
    except Exception as exc:  # AuthChallengeInvalid: not found, or not verified.
        raise ContactWriteError(str(exc)) from exc


def _demote(member, ids: list[str]) -> None:
    for contact in ContactEmail.objects.select_for_update().filter(pk__in=ids, member=member, email_type="secondary"):
        contact.email_type = "other"
        contact.save(update_fields=["email_type", "updated_at"])


def add_email(member, data: dict) -> None:
    """Add a new address: the listed secondaries become "other" first (one secondary per member)."""
    _demote(member, data.get("demote", []))
    ContactEmail.objects.create(
        member=member,
        email_address=data["address"],
        email_type=data["type"],
        verified=data["verified"],
        subscribe=data["subscribe"],
    )


def claim_email(member, ref: str, data: dict) -> None:
    """Attach a contact email that has no member. It must still have none, or nothing is changed."""
    _demote(member, data.get("demote", []))
    contact = ContactEmail.objects.select_for_update().filter(pk=ref, member__isnull=True).first()
    if contact is None:
        raise ContactWriteError("the contact email with no member was taken or removed after the review")
    contact.member = member
    contact.email_type = data["type"]
    contact.verified = data["verified"]
    contact.subscribe = data["subscribe"]
    contact.save(update_fields=["member", "email_type", "verified", "subscribe", "updated_at"])


def add_phone(member, data: dict) -> None:
    try:
        create_contact_phone(
            member=member, phone_number=data["number"], region=data["region"], subscribe=data["subscribe"]
        )
    except Exception as exc:  # AuthChallengeInvalid: the number was taken after the review.
        raise ContactWriteError(str(exc)) from exc


def delete_email(member, ref: str) -> None:
    try:
        delete_contact_email(member=member, contact_email_id=ref)
    except Exception as exc:  # LastRecoveryContactError / AuthChallengeInvalid.
        raise ContactWriteError(str(exc)) from exc


def delete_phone(member, ref: str) -> None:
    try:
        delete_contact_phone(member=member, contact_phone_id=ref)
    except Exception as exc:  # LastRecoveryContactError / AuthChallengeInvalid.
        raise ContactWriteError(str(exc)) from exc
