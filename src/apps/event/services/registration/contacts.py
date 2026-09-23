"""Validate event contact policies and consume proofs inside registration's transaction."""

from apps.authn.models import ContactEmail, ContactPhone
from apps.authn.services.contacts.contact_phones import normalize_to_national
from apps.authn.services.email.auth_email import normalize_email
from apps.authn.services.email.challenges import AuthChallengeInvalid, consume_verification_token


class RegistrationContactError(ValueError):
    """A submitted contact does not satisfy the selected event's policy."""

    def __init__(self, detail: str, *, code: str | None = None):
        self.code = code
        super().__init__(detail)


def registration_contact_fields(member, event, data):
    fields = {}
    _apply_secondary_email(member, event, data, fields)
    _apply_phone(member, event, data, fields)
    return fields


def _apply_secondary_email(member, event, data, fields):
    if not event.allow_secondary_email:
        return
    email = normalize_email(data.get("attendee_secondary_email", ""))
    if not email:
        if event.require_secondary_email:
            raise RegistrationContactError("A secondary email address is required for this event.")
        return
    if email == normalize_email(member.get_primary_email() or ""):
        raise RegistrationContactError("Secondary email must be different from the primary email.")

    verified = ContactEmail.objects.filter(member=member, email_address__iexact=email, verified=True).exists()
    if event.verify_secondary_email and not verified:
        challenge_id = data.get("secondary_email_verification_challenge_id")
        token = data.get("secondary_email_verification_token")
        if not challenge_id or not token:
            raise RegistrationContactError(
                "Please verify your secondary email before completing registration.",
                code="secondary_email_verification_required",
            )
        try:
            consume_verification_token(
                purpose="event_registration",
                verification_token=token,
                member=member,
                target_email=email,
                context_identifier=f"event-registration:{event.pk}",
                challenge_id=challenge_id,
            )
        except AuthChallengeInvalid as exc:
            raise RegistrationContactError(
                "Please verify your secondary email before completing registration.",
                code="secondary_email_verification_required",
            ) from exc
        verified = True

    fields.update(attendee_secondary_email=email, secondary_email_verified=verified)


def _apply_phone(member, event, data, fields):
    if not event.collect_phone:
        return
    phone = data.get("attendee_phone", "").strip()
    if not phone:
        if event.require_phone:
            raise RegistrationContactError("A phone number is required for this event.")
        return

    from apps.event.views.registration.phones import _normalize_phone, _validate_phone_digits

    region = "1-US"
    error = _validate_phone_digits(phone, region)
    if error:
        raise RegistrationContactError(error)
    phone = _normalize_phone(phone, region)
    verified = ContactPhone.objects.filter(
        member=member,
        phone_number=normalize_to_national(phone, region),
        region=region,
        verified=True,
    ).exists()
    if event.verify_phone and not verified:
        from apps.authn.services.sms import PhoneVerificationInvalid, consume_verified_phone_challenge
        from apps.event.views.registration.phones import LEGACY_EVENT_REGISTRATION_CONTEXT

        try:
            consume_verified_phone_challenge(
                phone_number=phone,
                purpose="event_registration",
                member=member,
                context_identifier=f"event-registration:{event.pk}",
                challenge_id=data.get("phone_verification_challenge_id"),
                compatibility_context_identifiers=(LEGACY_EVENT_REGISTRATION_CONTEXT,),
            )
        except PhoneVerificationInvalid as exc:
            raise RegistrationContactError(
                "Please verify your phone number before completing registration.",
                code="phone_verification_required",
            ) from exc
        verified = True

    fields.update(attendee_phone=phone, phone_verified=verified)
