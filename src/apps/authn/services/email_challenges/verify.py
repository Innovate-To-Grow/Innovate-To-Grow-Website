from __future__ import annotations

from collections.abc import Sequence

from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone

from apps.authn.models.security import EmailAuthChallenge

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
    import apps.authn.services.email_challenges as api

    # Lock the pending challenge row so concurrent verification attempts serialize.
    # Without the lock, two simultaneous wrong guesses can both read attempts=N and
    # both write N+1 (a lost update that under-counts and weakens brute-force limits),
    # and two simultaneous correct guesses could both succeed. select_for_update is a
    # no-op on SQLite (dev) and effective on PostgreSQL (prod).
    challenge = latest_pending_for_input(purposes=purposes, target_email=target_email, for_update=True)
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
    import apps.authn.services.email_challenges as api

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
    import apps.authn.services.email_challenges as api

    # Consume happens in a separate request/transaction from verify, so the
    # select_for_update lock taken during verify is no longer held. Flip the
    # status with a single conditional UPDATE that only matches a still-PENDING
    # row; if two requests both passed verification for the same code, only the
    # first flips it (1 row) and the loser sees 0 rows and is rejected — enforcing
    # one-time use regardless of database backend.
    updated = EmailAuthChallenge.objects.filter(
        pk=challenge.pk,
        status=EmailAuthChallenge.Status.PENDING,
    ).update(
        status=EmailAuthChallenge.Status.CONSUMED,
        updated_at=timezone.now(),
    )
    if not updated:
        raise api.AuthChallengeInvalid("Verification code is invalid or has expired.")
    challenge.status = EmailAuthChallenge.Status.CONSUMED


@transaction.atomic
def consume_verification_token(
    *,
    purpose: str,
    verification_token: str,
    member=None,
) -> EmailAuthChallenge:
    import apps.authn.services.email_challenges as api

    queryset = EmailAuthChallenge.objects.filter(
        purpose=purpose,
        status=EmailAuthChallenge.Status.VERIFIED,
    ).order_by("-verified_at", "-created_at")
    if member is not None:
        queryset = queryset.filter(member=member)

    # No arbitrary cap: the candidate set is tightly scoped (purpose + VERIFIED +
    # member) and at most one row can match a given token hash. A prior [:10] slice
    # could silently reject a valid token when >10 verified challenges existed for
    # the member/purpose.
    now = timezone.now()
    for challenge in queryset:
        if challenge.expires_at <= now:
            challenge.mark_expired()
            continue
        token_hash = challenge.verification_token_hash
        if token_hash and check_password(verification_token, token_hash):
            challenge.mark_consumed()
            return challenge

    raise api.AuthChallengeInvalid("Verification token is invalid or has expired.")
