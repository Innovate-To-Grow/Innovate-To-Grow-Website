"""
Service layer for managing contact emails (add, verify, delete).
"""

import logging
import threading

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from authn.models import ContactEmail
from authn.models.security import EmailAuthChallenge
from authn.services.email.auth_email import normalize_email, registration_email_conflicts
from authn.services.email_challenges import (
    AuthChallengeInvalid,
    consume_login_or_registration_challenge,
    issue_email_challenge,
    verify_email_code,
)

logger = logging.getLogger(__name__)

Member = get_user_model()

PURPOSE = EmailAuthChallenge.Purpose.CONTACT_EMAIL_VERIFY


def _member_has_secondary(member, exclude_pk=None):
    """Check whether the member already owns a secondary contact email."""
    qs = ContactEmail.objects.filter(member=member, email_type="secondary")
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return qs.exists()


def _notify_email_owner_in_background(email: str):
    """Send a claim-attempt notification to the owner of the email, in a daemon thread."""

    def _send():
        try:
            from authn.services.email.send_email import send_notification_email

            frontend_url = getattr(settings, "FRONTEND_URL", "").rstrip("/")
            account_url = f"{frontend_url}/account" if frontend_url else ""

            send_notification_email(
                recipient=email,
                subject="Security notice - Innovate to Grow",
                template="authn/email/email_claim_notification.html",
                context={"account_url": account_url},
            )
        except Exception:
            logger.exception("Failed to send email claim notification to %s", email)

    thread = threading.Thread(target=_send, daemon=True)
    thread.start()


def create_contact_email(*, member, email_address: str, email_type: str = "secondary", subscribe: bool = True):
    if email_type == "secondary" and _member_has_secondary(member):
        raise AuthChallengeInvalid(
            "You already have a secondary email. Change the existing one to 'other' first, or add this email as 'other'."
        )

    normalized = normalize_email(email_address)

    if registration_email_conflicts(normalized):
        _notify_email_owner_in_background(normalized)
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
        _notify_email_owner_in_background(normalized)
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


@transaction.atomic
def make_contact_email_primary(*, member, contact_email_id):
    """
    Set a verified non-primary contact email as primary.

    The previous primary becomes ``secondary`` (not deleted). Requires the target email to be verified.
    """
    contact = ContactEmail.objects.select_for_update().filter(pk=contact_email_id, member=member).first()
    if contact is None:
        raise AuthChallengeInvalid("Contact email not found.")

    if contact.email_type == "primary":
        return contact

    if not contact.verified:
        raise AuthChallengeInvalid("Verify this email before setting it as primary.")

    old_primary = (
        ContactEmail.objects.select_for_update()
        .filter(member=member, email_type="primary")
        .order_by("created_at")
        .first()
    )
    if old_primary:
        # Demote existing secondary to "other" before the old primary takes its slot
        existing_secondary = (
            ContactEmail.objects.select_for_update()
            .filter(member=member, email_type="secondary")
            .exclude(pk=contact.pk)
            .first()
        )
        if existing_secondary:
            existing_secondary.email_type = "other"
            existing_secondary.save(update_fields=["email_type", "updated_at"])

        old_primary.email_type = "secondary"
        old_primary.save(update_fields=["email_type", "updated_at"])

    contact.email_type = "primary"
    contact.save(update_fields=["email_type", "updated_at"])

    return contact
