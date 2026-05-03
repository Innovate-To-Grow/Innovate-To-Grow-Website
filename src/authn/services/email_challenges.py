from __future__ import annotations

import logging
import secrets
from collections.abc import Sequence
from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone

from authn.models.security import EmailAuthChallenge
from authn.services.email.auth_email import normalize_email

logger = logging.getLogger(__name__)

CHALLENGE_TTL = timedelta(minutes=10)
RESEND_COOLDOWN = timedelta(seconds=60)
MAX_CHALLENGES_PER_HOUR = 10


class AuthChallengeError(RuntimeError):
    """Base exception for auth challenge failures."""


class AuthChallengeInvalid(AuthChallengeError):
    """Raised when a code or token is invalid."""


class AuthChallengeThrottled(AuthChallengeError):
    """Raised when a code is requested too frequently."""


class AuthChallengeDeliveryError(AuthChallengeError):
    """Raised when the SES send fails."""


def _random_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _random_token() -> str:
    return secrets.token_urlsafe(32)


def _expire_queryset(queryset):
    queryset.exclude(status=EmailAuthChallenge.Status.EXPIRED).update(
        status=EmailAuthChallenge.Status.EXPIRED,
        updated_at=timezone.now(),
    )


def _get_latest_pending(*, purpose: str, target_email: str):
    return (
        EmailAuthChallenge.objects.filter(
            purpose=purpose,
            target_email__iexact=target_email,
            status=EmailAuthChallenge.Status.PENDING,
        )
        .order_by("-created_at")
        .first()
    )


def _get_latest_pending_for_purposes(*, purposes: Sequence[str], target_email: str):
    return (
        EmailAuthChallenge.objects.filter(
            purpose__in=purposes,
            target_email__iexact=target_email,
            status=EmailAuthChallenge.Status.PENDING,
        )
        .order_by("-created_at")
        .first()
    )


def _assert_within_limit(*, member, purpose: str, target_email: str, now):
    cutoff = now - timedelta(hours=1)
    sent_count = EmailAuthChallenge.objects.filter(
        member=member,
        purpose=purpose,
        target_email__iexact=target_email,
        created_at__gte=cutoff,
    ).count()
    if sent_count >= MAX_CHALLENGES_PER_HOUR:
        raise AuthChallengeThrottled("Too many verification codes requested. Please try again later.")

    latest = _get_latest_pending(purpose=purpose, target_email=target_email)
    if latest and latest.last_sent_at and now - latest.last_sent_at < RESEND_COOLDOWN:
        raise AuthChallengeThrottled("Please wait before requesting another code.")


@transaction.atomic
def _create_challenge_record(*, member, purpose: str, target_email: str) -> tuple[EmailAuthChallenge, str]:
    """Create the challenge DB record (atomic). Returns (challenge, plain_code)."""
    normalized_email = normalize_email(target_email)
    now = timezone.now()
    _assert_within_limit(member=member, purpose=purpose, target_email=normalized_email, now=now)

    _expire_queryset(
        EmailAuthChallenge.objects.filter(
            member=member,
            purpose=purpose,
            target_email__iexact=normalized_email,
            status__in=[EmailAuthChallenge.Status.PENDING, EmailAuthChallenge.Status.VERIFIED],
        )
    )

    code = _random_code()
    challenge = EmailAuthChallenge.objects.create(
        member=member,
        purpose=purpose,
        target_email=normalized_email,
        code_hash=make_password(code),
        expires_at=now + CHALLENGE_TTL,
        max_attempts=5,
        last_sent_at=now,
    )

    return challenge, code


def issue_email_challenge(
    *,
    member,
    purpose: str,
    target_email: str,
    link_flow: str | None = None,
    link_source: str | None = None,
) -> EmailAuthChallenge:
    """Create a challenge and send the verification code email."""
    from authn.services.email.send_email import send_verification_email

    challenge, plain_code = _create_challenge_record(
        member=member,
        purpose=purpose,
        target_email=target_email,
    )

    try:
        send_verification_email(
            recipient=challenge.target_email,
            code=plain_code,
            purpose=purpose,
            link_flow=link_flow,
            link_source=link_source,
        )
    except Exception as exc:
        logger.exception("Failed to send verification email")
        # Delete the challenge so it does not count toward the hourly
        # rate-limit or resend-cooldown on subsequent retry attempts.
        with transaction.atomic():
            EmailAuthChallenge.objects.filter(pk=challenge.pk).delete()
        raise AuthChallengeDeliveryError("Failed to send verification email.") from exc

    return challenge


@transaction.atomic
def verify_email_code(*, purpose: str, target_email: str, code: str) -> EmailAuthChallenge:
    return verify_email_code_for_purposes(purposes=[purpose], target_email=target_email, code=code)


@transaction.atomic
def verify_email_code_for_purposes(*, purposes: Sequence[str], target_email: str, code: str) -> EmailAuthChallenge:
    normalized_email = normalize_email(target_email)
    challenge = _get_latest_pending_for_purposes(purposes=purposes, target_email=normalized_email)
    if challenge is None:
        raise AuthChallengeInvalid("Verification code is invalid or has expired.")

    if challenge.is_expired:
        challenge.mark_expired()
        raise AuthChallengeInvalid("Verification code is invalid or has expired.")

    if challenge.attempts >= challenge.max_attempts:
        challenge.mark_expired()
        raise AuthChallengeInvalid("Verification code is invalid or has expired.")

    if not check_password(code, challenge.code_hash):
        challenge.attempts += 1
        if challenge.attempts >= challenge.max_attempts:
            challenge.status = EmailAuthChallenge.Status.EXPIRED
        challenge.save(update_fields=["attempts", "status", "updated_at"])
        raise AuthChallengeInvalid("Verification code is invalid or has expired.")

    return challenge


@transaction.atomic
def mark_challenge_verified(challenge: EmailAuthChallenge) -> str:
    verification_token = _random_token()
    challenge.status = EmailAuthChallenge.Status.VERIFIED
    challenge.verified_at = timezone.now()
    challenge.verification_token_hash = make_password(verification_token)
    challenge.expires_at = timezone.now() + CHALLENGE_TTL
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
def consume_verification_token(*, purpose: str, verification_token: str, member=None) -> EmailAuthChallenge:
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
        if challenge.verification_token_hash and check_password(verification_token, challenge.verification_token_hash):
            challenge.mark_consumed()
            return challenge

    raise AuthChallengeInvalid("Verification token is invalid or has expired.")
