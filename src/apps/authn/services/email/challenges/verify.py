"""Checking an emailed code: the attempt counting, the wrong-guess record and the state transition it makes."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone

from apps.authn.models.security import EmailAuthChallenge

from .queries import latest_pending_for_input


def verify_email_code(
    *,
    purpose: str,
    target_email: str,
    code: str,
    member=None,
    approved_callback: Callable[[EmailAuthChallenge], Any] | None = None,
) -> Any:
    return verify_email_code_for_purposes(
        purposes=[purpose],
        target_email=target_email,
        code=code,
        member=member,
        approved_callback=approved_callback,
    )


def verify_email_code_for_purposes(
    *,
    purposes: Sequence[str],
    target_email: str,
    code: str,
    member=None,
    approved_callback: Callable[[EmailAuthChallenge], Any] | None = None,
) -> Any:
    # Keep the successful transition and caller completion work in one
    # transaction. Public login/register callers use the callback to lock and
    # update the member/contact and mint JWTs before code consumption can
    # commit. Invalid outcomes leave the block normally, so attempt/expiry
    # changes commit before the public exception is raised below.
    callback_result = None
    with transaction.atomic():
        challenge, _, error = _verify_and_transition_email_code(
            purposes=purposes,
            target_email=target_email,
            code=code,
            target_status=EmailAuthChallenge.Status.CONSUMED,
            member=member,
        )
        if challenge is not None and approved_callback is not None:
            callback_result = approved_callback(challenge)
    if error or challenge is None:
        import apps.authn.services.email.challenges as api

        raise api.AuthChallengeInvalid(error or "Verification code is invalid or has expired.")
    return callback_result if approved_callback is not None else challenge


def verify_email_code_and_mint_token(
    *,
    purpose: str,
    target_email: str,
    code: str,
    member=None,
    challenge_id=None,
    context_identifier: str | None = None,
) -> tuple[EmailAuthChallenge, str]:
    """Verify a code and atomically transition it to a token-bearing state.

    Password/account confirmation flows need a second request after code entry.
    The code check and ``PENDING -> VERIFIED`` transition therefore happen in
    one locked transaction, and the plaintext token is returned only to the
    caller that won the conditional update.
    """
    challenge, verification_token, error = _verify_and_transition_email_code(
        purposes=[purpose],
        target_email=target_email,
        code=code,
        target_status=EmailAuthChallenge.Status.VERIFIED,
        member=member,
        challenge_id=challenge_id,
        context_identifier=context_identifier,
    )
    if error or challenge is None or verification_token is None:
        import apps.authn.services.email.challenges as api

        raise api.AuthChallengeInvalid(error or "Verification code is invalid or has expired.")
    return challenge, verification_token


def _record_wrong_guess(challenge: EmailAuthChallenge) -> None:
    challenge.attempts += 1
    if challenge.attempts >= challenge.max_attempts:
        challenge.status = EmailAuthChallenge.Status.EXPIRED
    challenge.save(update_fields=["attempts", "status", "updated_at"])


def _transition_values(target_status: str, now) -> tuple[dict, str | None]:
    """Column values for the pending -> ``target_status`` update, and the new token when verifying."""
    update_values = {"status": target_status, "verified_at": now, "updated_at": now}
    if target_status == EmailAuthChallenge.Status.CONSUMED:
        return update_values, None
    if target_status != EmailAuthChallenge.Status.VERIFIED:
        raise ValueError(f"Unsupported email challenge target status: {target_status}")
    import apps.authn.services.email.challenges as api

    verification_token = api._random_token()
    update_values.update(
        verification_token_hash=make_password(verification_token),
        expires_at=now + api.CHALLENGE_TTL,
    )
    return update_values, verification_token


@transaction.atomic
def _verify_and_transition_email_code(
    *,
    purposes: Sequence[str],
    target_email: str,
    code: str,
    target_status: str,
    member=None,
    challenge_id=None,
    context_identifier: str | None = None,
) -> tuple[EmailAuthChallenge | None, str | None, str]:
    # Lock the pending challenge row so concurrent verification attempts serialize.
    # Without the lock, two simultaneous wrong guesses can both read attempts=N and
    # both write N+1 (a lost update that under-counts and weakens brute-force limits),
    # and two simultaneous correct guesses could both succeed. The conditional
    # status update below remains the final one-time-use guard.
    challenge = latest_pending_for_input(
        purposes=purposes,
        target_email=target_email,
        for_update=True,
        # Preserve historical lookup behavior for unscoped authentication callers.
        member=member if challenge_id is not None or context_identifier is not None else None,
        challenge_id=challenge_id,
        context_identifier=context_identifier,
    )
    if challenge is None:
        return None, None, "Verification code is invalid or has expired."

    if member is not None and challenge.member_id != member.pk:
        return None, None, "Verification code is invalid or has expired."

    if challenge.is_expired or challenge.attempts >= challenge.max_attempts:
        challenge.mark_expired()
        return None, None, "Verification code is invalid or has expired."

    if not check_password(code, challenge.code_hash):
        _record_wrong_guess(challenge)
        return None, None, "Verification code is invalid or has expired."

    now = timezone.now()
    update_values, verification_token = _transition_values(target_status, now)
    updated = EmailAuthChallenge.objects.filter(
        pk=challenge.pk,
        status=EmailAuthChallenge.Status.PENDING,
        expires_at__gt=now,
    ).update(**update_values)
    if not updated:
        return None, None, "Verification code is invalid or has expired."

    challenge.status = target_status
    challenge.verified_at = now
    if target_status == EmailAuthChallenge.Status.VERIFIED:
        challenge.expires_at = update_values["expires_at"]
    return challenge, verification_token, ""
