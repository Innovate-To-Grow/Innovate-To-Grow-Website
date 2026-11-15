"""
Service layer for managing contact emails (add, verify, delete).
"""

import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from apps.authn.models import ContactEmail
from apps.authn.models.security import EmailAuthChallenge
from apps.authn.services.email.auth_email import normalize_email, registration_email_conflicts
from apps.authn.services.email.challenges import (
    AuthChallengeInvalid,
    issue_email_challenge,
    verify_email_code,
)
from apps.core.services.helpers.in_process import start_in_process_task

# Re-exported: the contacts package, the member import, the primary switch and mail's address actions import them here.
from .contact_email_changes import delete_contact_email as delete_contact_email
from .contact_email_changes import make_contact_email_primary as make_contact_email_primary

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
    """Queue an owner notification, or use the legacy in-process fallback."""
    frontend_url = getattr(settings, "FRONTEND_URL", "").rstrip("/")
    account_url = f"{frontend_url}/account" if frontend_url else ""
    notification = {
        "recipient": email,
        "subject": "Security notice - Innovate to Grow",
        "template": "authn/email/email_claim_notification.html",
        "context": {"account_url": account_url},
    }

    if getattr(settings, "BACKGROUND_JOBS_ENABLED", False):
        try:
            from apps.authn.services.email.send_email.notification_jobs import enqueue_notification_email

            enqueue_notification_email(**notification)
        except Exception:
            logger.exception("Failed to enqueue email claim notification to %s", email)
        return

    start_in_process_task(
        _send_email_owner_notification,
        notification,
        name="email-owner-security-notice",
        best_effort_start=True,
    )


def _send_email_owner_notification(notification: dict) -> None:
    try:
        from apps.authn.services.email.send_email import send_notification_email

        send_notification_email(**notification)
    except Exception:
        logger.exception("Failed to send email claim notification")


def create_contact_email(*, member, email_address: str, email_type: str = "secondary", subscribe: bool = True):
    normalized = normalize_email(email_address)

    if registration_email_conflicts(normalized):
        _notify_email_owner_in_background(normalized)
        raise AuthChallengeInvalid("This email address is already in use.")

    # Decide the type and insert atomically so the "does the member already have a
    # primary?" check can't race with a concurrent add. A member must hold exactly
    # one primary once they own any email, so the first email (or any email added
    # while the account has no primary — e.g. a legacy gap) is forced to primary,
    # regardless of the requested type. Verification status stays independent
    # (assigning primary never marks the email verified).
    try:
        with transaction.atomic():
            Member.objects.select_for_update().get(pk=member.pk)
            existing = list(ContactEmail.objects.select_for_update().filter(member=member))
            has_primary = any(c.email_type == "primary" for c in existing)
            effective_type = "primary" if not has_primary else email_type

            if effective_type == "secondary" and any(c.email_type == "secondary" for c in existing):
                raise AuthChallengeInvalid(
                    "You already have a secondary email. Change the existing one to 'other' first, "
                    "or add this email as 'other'."
                )

            contact_email = ContactEmail.objects.create(
                member=member,
                email_address=normalized,
                email_type=effective_type,
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

    def mark_contact_verified(_challenge):
        locked_contact = (
            ContactEmail.objects.select_for_update()
            .filter(
                pk=contact_email.pk,
                member=member,
                email_address__iexact=contact_email.email_address,
            )
            .first()
        )
        if locked_contact is None:
            raise AuthChallengeInvalid("Contact email not found.")
        if not locked_contact.verified:
            locked_contact.verified = True
            locked_contact.save(update_fields=["verified", "updated_at"])
        return locked_contact

    return verify_email_code(
        purpose=PURPOSE,
        target_email=contact_email.email_address,
        code=code,
        member=member,
        approved_callback=mark_contact_verified,
    )


def resend_contact_email_verification(*, member, contact_email_id):
    contact_email = ContactEmail.objects.filter(pk=contact_email_id, member=member).first()
    if contact_email is None:
        raise AuthChallengeInvalid("Contact email not found.")

    if contact_email.verified:
        raise AuthChallengeInvalid("This email is already verified.")

    issue_email_challenge(member=member, purpose=PURPOSE, target_email=contact_email.email_address)

    return {"message": "Verification code sent."}
