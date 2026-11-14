"""What a verified email code completes: a login, a registration, or either one for the unified email flow."""

from django.contrib.auth import get_user_model

from apps.authn.models.security import EmailAuthChallenge
from apps.authn.services import AuthChallengeInvalid

from ...shared.responses import build_auth_success_payload

Member = get_user_model()


def _link_email_subscriber(member):
    """Link anonymous ContactEmail records to a newly activated member."""
    from apps.authn.models import ContactEmail

    primary_email = member.get_primary_email()
    if primary_email:
        ContactEmail.objects.filter(
            email_address__iexact=primary_email,
            member__isnull=True,
        ).update(member=member)


def _mark_contact_email_verified(member, email_address):
    """Mark the member's ContactEmail as verified after successful code verification."""
    from apps.authn.models import ContactEmail

    ContactEmail.objects.filter(
        member=member,
        email_address__iexact=email_address,
        verified=False,
    ).update(verified=True)


def _lock_challenge_member(challenge):
    """Serialize auth completion against account/contact mutations."""
    return Member.objects.select_for_update().get(pk=challenge.member_id)


def _complete_login(challenge):
    member = _lock_challenge_member(challenge)
    if not member.is_active:
        raise AuthChallengeInvalid("Verification code is invalid or has expired.")
    _mark_contact_email_verified(member, challenge.target_email)
    return build_auth_success_payload(member, "Login successful.")


def _complete_registration(challenge):
    member = _lock_challenge_member(challenge)
    if not member.is_active:
        if not member.registration_pending:
            # Deactivated after the code was issued (or never a self-service signup):
            # proving email ownership must not revive it.
            raise AuthChallengeInvalid("Verification code is invalid or has expired.")
        member.is_active = True
        member.registration_pending = False
        member.save(update_fields=["is_active", "registration_pending", "updated_at"])
        _link_email_subscriber(member)
    _mark_contact_email_verified(member, challenge.target_email)
    return build_auth_success_payload(member, "Email verified. Registration successful.")


def _complete_unified_auth(challenge):
    if challenge.purpose == EmailAuthChallenge.Purpose.REGISTER:
        return _complete_registration(challenge)
    return _complete_login(challenge)
