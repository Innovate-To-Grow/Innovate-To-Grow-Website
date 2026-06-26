"""SMS-channel verification for the password create/change/reset flows.

The email password flows verify a code and then mint a one-time ``verification_token``
that the confirm step consumes via the channel-blind ``consume_verification_token``.
This module gives the SMS channel the same shape: it reuses the existing SMS OTP
infrastructure to verify the code, then mints a VERIFIED ``EmailAuthChallenge`` row
(``channel="sms"``) carrying the token — so the confirm endpoints stay unchanged.
"""

from __future__ import annotations

from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.utils import timezone

from apps.authn.models.security import EmailAuthChallenge
from apps.authn.services.email_challenges import CHALLENGE_TTL, _random_token
from apps.authn.services.sms import check_phone_verification, start_phone_verification


def request_sms_password_code(*, e164: str) -> None:
    """Send an SMS OTP for a password flow, reusing the shared OTP infrastructure
    (cache-stored hashed code, per-number send cap, TTL, attempt limit)."""
    start_phone_verification(e164)


@transaction.atomic
def verify_sms_password_code_and_mint(*, member, purpose: str, e164: str, code: str) -> str:
    """Verify an SMS OTP and mint a verification token for ``purpose``.

    Returns the plaintext token (only its hash is stored). Raises
    ``PhoneVerificationInvalid`` / ``PhoneVerificationThrottled`` from the OTP layer
    when the code is wrong, expired, reused, or over-attempted — in which case no
    token row is created.
    """
    check_phone_verification(e164, code)

    # Supersede any earlier unconsumed SMS challenge for this member+purpose so only
    # the freshest token is consumable (mirrors the email flow's expire-on-issue).
    EmailAuthChallenge.objects.filter(
        member=member,
        purpose=purpose,
        channel=EmailAuthChallenge.Channel.SMS,
        status__in=[EmailAuthChallenge.Status.PENDING, EmailAuthChallenge.Status.VERIFIED],
    ).update(status=EmailAuthChallenge.Status.EXPIRED, updated_at=timezone.now())

    token = _random_token()
    now = timezone.now()
    EmailAuthChallenge.objects.create(
        member=member,
        purpose=purpose,
        channel=EmailAuthChallenge.Channel.SMS,
        target_phone=e164,
        target_email="",
        code_hash="",
        verification_token_hash=make_password(token),
        verified_at=now,
        expires_at=now + CHALLENGE_TTL,
        status=EmailAuthChallenge.Status.VERIFIED,
    )
    return token
