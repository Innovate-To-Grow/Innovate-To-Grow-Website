"""
Service layer for managing contact phones (add, delete, normalize).
"""

import re

from django.db import IntegrityError

from authn.models import ContactPhone
from authn.models.contact.phone_regions import PHONE_REGION_CHOICES
from authn.services.email_challenges import AuthChallengeInvalid

# Country-code prefixes sorted longest-first so "852" matches before "8".
# For codes like "1-US" / "1-CA" the dial prefix is just "1".
_REGION_BY_CC: list[tuple[str, str]] = []


def _build_region_lookup() -> list[tuple[str, str]]:
    if _REGION_BY_CC:
        return _REGION_BY_CC
    for code, _label in PHONE_REGION_CHOICES:
        cc = code.split("-")[0] if "-" in code else code
        _REGION_BY_CC.append((cc, code))
    _REGION_BY_CC.sort(key=lambda t: len(t[0]), reverse=True)
    return _REGION_BY_CC


def _get_country_code(region: str) -> str:
    """Extract the dial prefix from a region code (e.g. '1-US' → '1', '86' → '86')."""
    return region.split("-")[0] if "-" in region else region


def normalize_to_national(phone: str, region: str) -> str:
    """Strip formatting and country-code prefix, returning national digits only.

    Input may be E.164 (``+12095765113``), national with formatting
    (``(209) 576-5113``), or already clean national (``2095765113``).
    """
    digits = re.sub(r"\D", "", phone.strip())
    cc = _get_country_code(region)
    if digits.startswith(cc):
        digits = digits[len(cc) :]
    return digits


def national_to_e164(phone: str, region: str) -> str:
    """Reconstruct an E.164 number from national digits + region."""
    cc = _get_country_code(region)
    digits = re.sub(r"\D", "", phone.strip())
    if digits.startswith(cc):
        return f"+{digits}"
    return f"+{cc}{digits}"


def infer_region_from_e164(phone: str, current_region: str = "") -> str:
    """Infer the PHONE_REGION_CHOICES code from an E.164 phone number.

    For +1 (shared by US and Canada), preserves *current_region* when it is
    already ``"1-CA"``; otherwise defaults to ``"1-US"``.
    """
    lookup = _build_region_lookup()
    digits = re.sub(r"\D", "", phone)

    for cc, region_code in lookup:
        if digits.startswith(cc):
            if cc == "1":
                return current_region if current_region == "1-CA" else "1-US"
            return region_code

    return current_region or "1-US"


def _to_national_digits(phone_number: str, region: str) -> str:
    """Normalize any phone input to national digits for DB storage.

    Handles: raw national digits, formatted national, or E.164 with country code.
    """
    cleaned = re.sub(r"[\s()\-.]", "", phone_number.strip())
    if cleaned.startswith("+"):
        cleaned = cleaned[1:]
    cc = _get_country_code(region)
    if cleaned.startswith(cc) and len(cleaned) > len(cc):
        cleaned = cleaned[len(cc) :]
    return re.sub(r"\D", "", cleaned)


def create_contact_phone(*, member, phone_number: str, region: str, subscribe: bool = False):
    national = _to_national_digits(phone_number, region)

    try:
        contact_phone = ContactPhone.objects.create(
            member=member,
            phone_number=national,
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

    e164 = national_to_e164(contact_phone.phone_number, contact_phone.region)
    start_phone_verification(e164)
    return {"message": "Verification code sent via SMS."}


def verify_phone_code(*, member, contact_phone_id, code: str):
    """Verify a Twilio OTP code and mark the phone as verified."""
    from authn.services.sms import check_phone_verification

    contact_phone = ContactPhone.objects.filter(pk=contact_phone_id, member=member).first()
    if contact_phone is None:
        raise AuthChallengeInvalid("Contact phone not found.")

    e164 = national_to_e164(contact_phone.phone_number, contact_phone.region)
    check_phone_verification(e164, code)

    contact_phone.verified = True
    contact_phone.save(update_fields=["verified", "updated_at"])
    return contact_phone
