"""
Service layer for managing contact emails (add, verify, delete).
"""

from django.contrib.auth import get_user_model
from django.db import IntegrityError

from authn.models import ContactEmail
from authn.models.security import EmailAuthChallenge
from authn.services.email.auth_email import normalize_email, registration_email_conflicts
from authn.services.email_challenges import (
    AuthChallengeInvalid,
    consume_login_or_registration_challenge,
    issue_email_challenge,
    verify_email_code,
)

Member = get_user_model()

PURPOSE = EmailAuthChallenge.Purpose.CONTACT_EMAIL_VERIFY


def create_contact_email(*, member, email_address: str, email_type: str = "secondary", subscribe: bool = False):
    normalized = normalize_email(email_address)

    if registration_email_conflicts(normalized):
        raise AuthChallengeInvalid("This email address is already in use.")

    try:
        contact_email = ContactEmail.objects.create(
            member=member,
            email_address=normalized,
            email_type=email_type,
            subscribe=subscribe,
            verified=False,
        )
    except IntegrityError:
        raise AuthChallengeInvalid("This email address is already in use.")

    issue_email_challenge(member=member, purpose=PURPOSE, target_email=normalized)

    return contact_email


def verify_contact_email_code(*, member, contact_email_id, code: str):
    contact_email = ContactEmail.objects.filter(pk=contact_email_id, member=member).first()
    if contact_email is None:
        raise AuthChallengeInvalid("Contact email not found.")

    challenge = verify_email_code(purpose=PURPOSE, target_email=contact_email.email_address, code=code)
    consume_login_or_registration_challenge(challenge)

    contact_email.verified = True
    contact_email.save(update_fields=["verified", "updated_at"])

    return contact_email


def resend_contact_email_verification(*, member, contact_email_id):
    contact_email = ContactEmail.objects.filter(pk=contact_email_id, member=member).first()
    if contact_email is None:
        raise AuthChallengeInvalid("Contact email not found.")

    if contact_email.verified:
        raise AuthChallengeInvalid("This email is already verified.")

    issue_email_challenge(member=member, purpose=PURPOSE, target_email=contact_email.email_address)

    return {"message": "Verification code sent."}


def delete_contact_email(*, member, contact_email_id):
    contact_email = ContactEmail.objects.filter(pk=contact_email_id, member=member).first()
    if contact_email is None:
        raise AuthChallengeInvalid("Contact email not found.")

    contact_email.delete()
