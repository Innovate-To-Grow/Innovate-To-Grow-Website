from __future__ import annotations

from collections.abc import Sequence

from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone

from authn.models.security import EmailAuthChallenge

from .queries import latest_pending_for_input


@transaction.atomic
def verify_email_code(
    *,
    purpose: str,
    target_email: str,
    code: str,
) -> EmailAuthChallenge:
    return verify_email_code_for_purposes(
        purposes=[purpose],
        target_email=target_email,
        code=code,
    )


@transaction.atomic
def verify_email_code_for_purposes(
    *,
    purposes: Sequence[str],
    target_email: str,
    code: str,
) -> EmailAuthChallenge:
    import authn.services.email_challenges as api

    challenge = latest_pending_for_input(purposes=purposes, target_email=target_email)
    if challenge is None:
        raise api.AuthChallengeInvalid("Verification code is invalid or has expired.")

    if challenge.is_expired or challenge.attempts >= challenge.max_attempts:
        challenge.mark_expired()
        raise api.AuthChallengeInvalid("Verification code is invalid or has expired.")

    if not check_password(code, challenge.code_hash):
        challenge.attempts += 1
        if challenge.attempts >= challenge.max_attempts:
            challenge.status = EmailAuthChallenge.Status.EXPIRED
        challenge.save(update_fields=["attempts", "status", "updated_at"])
        raise api.AuthChallengeInvalid("Verification code is invalid or has expired.")

    return challenge


@transaction.atomic
def mark_challenge_verified(challenge: EmailAuthChallenge) -> str:
    import authn.services.email_challenges as api

    verification_token = api._random_token()
    challenge.status = EmailAuthChallenge.Status.VERIFIED
    challenge.verified_at = timezone.now()
    challenge.verification_token_hash = make_password(verification_token)
    challenge.expires_at = timezone.now() + api.CHALLENGE_TTL
    challenge.save(
        update_fields=[
            "status",
            "verified_at",
            "verification_token_hash",
            "expires_at",
            "updated_at",
        ]
    )
    return verification_token


def consume_login_or_registration_challenge(challenge: EmailAuthChallenge):
    challenge.mark_consumed()


@transaction.atomic
def consume_verification_token(
    *,
    purpose: str,
    verification_token: str,
    member=None,
) -> EmailAuthChallenge:
    import authn.services.email_challenges as api

    queryset = EmailAuthChallenge.objects.filter(
        purpose=purpose,
        status=EmailAuthChallenge.Status.VERIFIED,
    ).order_by("-verified_at", "-created_at")
    if member is not None:
        queryset = queryset.filter(member=member)

    now = timezone.now()
    for challenge in queryset[:10]:
        if challenge.expires_at <= now:
            challenge.mark_expired()
            continue
        token_hash = challenge.verification_token_hash
        if token_hash and check_password(verification_token, token_hash):
            challenge.mark_consumed()
            return challenge

    raise api.AuthChallengeInvalid("Verification token is invalid or has expired.")
