"""
Service layer for managing contact phones (add, delete).
"""

from django.db import IntegrityError

from authn.models import ContactPhone
from authn.services.email_challenges import AuthChallengeInvalid


def _normalize_phone_number(phone_number: str, region: str) -> str:
    """
    Normalize a phone number to international E.164 format.

    If the number already starts with '+', return as-is.
    Otherwise, prepend '+' and the country code extracted from the region.
    """
    if phone_number.startswith("+"):
        return phone_number

    country_code = region.split("-")[0] if "-" in region else region
    return f"+{country_code}{phone_number}"


def create_contact_phone(*, member, phone_number: str, region: str, subscribe: bool = False):
    normalized = _normalize_phone_number(phone_number, region)

    try:
        # Reclaim a soft-deleted row to avoid unique-constraint violation
        deleted_qs = ContactPhone.all_objects.filter(phone_number=normalized, is_deleted=True)
        if deleted_qs.exists():
            contact_phone = deleted_qs.first()
            contact_phone.member = member
            contact_phone.region = region
            contact_phone.verified = False
            contact_phone.subscribe = subscribe
            contact_phone.is_deleted = False
            contact_phone.deleted_at = None
            contact_phone.save(
                update_fields=[
                    "member_id",
                    "region",
                    "verified",
                    "subscribe",
                    "is_deleted",
                    "deleted_at",
                    "updated_at",
                ]
            )
        else:
            contact_phone = ContactPhone.objects.create(
                member=member,
                phone_number=normalized,
                region=region,
                verified=False,
                subscribe=subscribe,
            )
    except IntegrityError:
        raise AuthChallengeInvalid("This phone number is already in use.")

    return contact_phone


def delete_contact_phone(*, member, contact_phone_id):
    contact_phone = ContactPhone.objects.filter(pk=contact_phone_id, member=member).first()
    if contact_phone is None:
        raise AuthChallengeInvalid("Contact phone not found.")

    contact_phone.delete()


def request_phone_verification(*, member, contact_phone_id):
    """Start Twilio OTP verification for a contact phone."""
    from authn.services.sms import start_phone_verification

    contact_phone = ContactPhone.objects.filter(pk=contact_phone_id, member=member).first()
    if contact_phone is None:
        raise AuthChallengeInvalid("Contact phone not found.")
    if contact_phone.verified:
        raise AuthChallengeInvalid("This phone number is already verified.")

    start_phone_verification(contact_phone.phone_number)
    return {"message": "Verification code sent via SMS."}


def verify_phone_code(*, member, contact_phone_id, code: str):
    """Verify a Twilio OTP code and mark the phone as verified."""
    from authn.services.sms import check_phone_verification

    contact_phone = ContactPhone.objects.filter(pk=contact_phone_id, member=member).first()
    if contact_phone is None:
        raise AuthChallengeInvalid("Contact phone not found.")

    check_phone_verification(contact_phone.phone_number, code)

    contact_phone.verified = True
    contact_phone.save(update_fields=["verified", "updated_at"])
    return contact_phone
