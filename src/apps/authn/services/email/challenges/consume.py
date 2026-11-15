"""Using a verified challenge: marking it verified, and consuming a login or registration challenge or a
verification token exactly once."""

from __future__ import annotations

from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone

from apps.authn.models.security import EmailAuthChallenge
from apps.authn.services.email.auth_email import normalize_email


@transaction.atomic
def mark_challenge_verified(challenge: EmailAuthChallenge) -> str:
    import apps.authn.services.email.challenges as api

    locked = EmailAuthChallenge.objects.select_for_update().filter(pk=challenge.pk).first()
    if locked is None or locked.status != EmailAuthChallenge.Status.PENDING or locked.is_expired:
        raise api.AuthChallengeInvalid("Verification code is invalid or has expired.")

    verification_token = api._random_token()
    now = timezone.now()
    new_expires_at = now + api.CHALLENGE_TTL
    updated = EmailAuthChallenge.objects.filter(
        pk=locked.pk,
        status=EmailAuthChallenge.Status.PENDING,
        expires_at__gt=now,
    ).update(
        status=EmailAuthChallenge.Status.VERIFIED,
        verified_at=now,
        verification_token_hash=make_password(verification_token),
        expires_at=new_expires_at,
        updated_at=now,
    )
    if not updated:
        raise api.AuthChallengeInvalid("Verification code is invalid or has expired.")
    challenge.status = EmailAuthChallenge.Status.VERIFIED
    challenge.verified_at = now
    challenge.expires_at = new_expires_at
    return verification_token


def consume_login_or_registration_challenge(challenge: EmailAuthChallenge):
    import apps.authn.services.email.challenges as api

    # Consume happens in a separate request/transaction from verify, so the
    # select_for_update lock taken during verify is no longer held. Flip the
    # status with a single conditional UPDATE that only matches a still-PENDING
    # row; if two requests both passed verification for the same code, only the
    # first flips it (1 row) and the loser sees 0 rows and is rejected — enforcing
    # one-time use regardless of database backend.
    now = timezone.now()
    updated = EmailAuthChallenge.objects.filter(
        pk=challenge.pk,
        status=EmailAuthChallenge.Status.PENDING,
        expires_at__gt=now,
    ).update(
        status=EmailAuthChallenge.Status.CONSUMED,
        updated_at=now,
    )
    if not updated:
        EmailAuthChallenge.objects.filter(
            pk=challenge.pk,
            status=EmailAuthChallenge.Status.PENDING,
            expires_at__lte=now,
        ).update(status=EmailAuthChallenge.Status.EXPIRED, updated_at=now)
        raise api.AuthChallengeInvalid("Verification code is invalid or has expired.")
    challenge.status = EmailAuthChallenge.Status.CONSUMED


def consume_verification_token(
    *,
    purpose: str,
    verification_token: str,
    member=None,
    target_email: str | None = None,
    context_identifier: str | None = None,
    challenge_id=None,
) -> EmailAuthChallenge:
    challenge = _consume_verification_token(
        purpose=purpose,
        verification_token=verification_token,
        member=member,
        target_email=target_email,
        context_identifier=context_identifier,
        challenge_id=challenge_id,
    )
    if challenge is None:
        import apps.authn.services.email.challenges as api

        raise api.AuthChallengeInvalid("Verification token is invalid or has expired.")
    return challenge


@transaction.atomic
def _consume_verification_token(
    *,
    purpose: str,
    verification_token: str,
    member=None,
    target_email: str | None = None,
    context_identifier: str | None = None,
    challenge_id=None,
) -> EmailAuthChallenge | None:
    queryset = (
        EmailAuthChallenge.objects.select_for_update()
        .filter(
            purpose=purpose,
            status=EmailAuthChallenge.Status.VERIFIED,
        )
        .order_by("-verified_at", "-created_at")
    )
    if member is not None:
        queryset = queryset.filter(member=member)
    if target_email is not None:
        queryset = queryset.filter(target_email__iexact=normalize_email(target_email))
    if context_identifier is not None:
        queryset = queryset.filter(context_identifier=context_identifier)
    if challenge_id is not None:
        queryset = queryset.filter(pk=challenge_id)

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
            updated = EmailAuthChallenge.objects.filter(
                pk=challenge.pk,
                status=EmailAuthChallenge.Status.VERIFIED,
                expires_at__gt=now,
            ).update(
                status=EmailAuthChallenge.Status.CONSUMED,
                updated_at=now,
            )
            if updated:
                challenge.status = EmailAuthChallenge.Status.CONSUMED
                return challenge

    return None
