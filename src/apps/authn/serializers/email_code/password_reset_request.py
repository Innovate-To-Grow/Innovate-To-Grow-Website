"""Password reset, step 1: send a reset code to the email address or phone number given (enumeration-safe)."""

from __future__ import annotations

import logging
import uuid

from rest_framework import serializers

from apps.authn.services import (
    AuthChallengeDeliveryError,
    AuthChallengeThrottled,
    PhoneVerificationError,
    PhoneVerificationInvalid,
    PhoneVerificationThrottled,
    issue_email_challenge,
    normalize_email,
    request_sms_password_code,
    resolve_login_identifier,
)

from .base import PURPOSE

logger = logging.getLogger(__name__)


def _identifier_value(data: dict) -> str:
    """Read the login identifier from ``identifier`` (preferred) or the legacy ``email`` alias."""
    return (data.get("identifier") or data.get("email") or "").strip()


class PasswordResetRequestSerializer(serializers.Serializer):
    """Request a password-reset code by email or phone (enumeration-safe).

    Accepts ``identifier`` (an email address or a phone number); ``email`` is kept
    as a backward-compatible alias. The response is identical whether or not an
    account exists, and the channel follows the identifier the caller supplied.
    """

    identifier = serializers.CharField(required=False, allow_blank=True, max_length=254)
    email = serializers.CharField(required=False, allow_blank=True, max_length=254)

    def validate(self, attrs: dict) -> dict:
        from apps.authn.services.contacts.contact_phones import national_to_e164, normalize_to_national

        identifier = _identifier_value(attrs)
        if not identifier:
            raise serializers.ValidationError({"identifier": "An email or phone number is required."})
        resolved = resolve_login_identifier(identifier, require_active=True)
        attrs["resolved"] = resolved
        if resolved is not None:
            kind = "phone" if resolved.via == "phone" else "email"
            destination = resolved.e164 if kind == "phone" else resolved.email
        elif "@" not in identifier and any(ch.isdigit() for ch in identifier):
            kind = "phone"
            destination = national_to_e164(normalize_to_national(identifier, "1-US"), "1-US")
        else:
            kind, destination = "email", normalize_email(identifier)
        attrs["destination_kind"] = kind
        attrs["destination_normalized"] = destination
        return attrs

    def save(self):
        from apps.authn.models import SendVerificationRequest
        from apps.authn.services.send_verification.exceptions import SendVerificationError
        from apps.authn.services.send_verification.outcomes import SendOutcome, public_reset_payload

        challenge_id = str(uuid.uuid4())
        resolved = self.validated_data["resolved"]
        outcome = SendVerificationRequest.Status.DEFINITELY_FAILED
        try:
            if resolved is not None:
                challenge_id = _send_reset_code(resolved) or challenge_id
                outcome = SendVerificationRequest.Status.PROVIDER_ACCEPTED
        except (
            AuthChallengeDeliveryError,
            AuthChallengeThrottled,
            PhoneVerificationError,
            SendVerificationError,
        ) as exc:
            # ``SendVerificationError`` here is the SMS daily budget being spent at dispatch: nothing was sent, and
            # the caller still gets the neutral answer below, exactly as for a number without an account. A 429
            # would only ever be seen for a number that HAS an account.
            challenge_id = str(getattr(exc, "challenge_id", "") or challenge_id)
            outcome = _reset_failure_outcome(exc)
            logger.warning("Password-reset delivery did not complete", exc_info=True)
        payload = public_reset_payload(challenge_id)
        self.send_outcome = SendOutcome(
            payload,
            202,
            outcome,
            challenge_id if resolved is not None and resolved.via == "phone" else "",
        )
        return payload


def _send_reset_code(resolved) -> str | None:
    """Send the reset code over the resolved channel; the SMS challenge id when one was issued."""
    if resolved.via == "email":
        issue_email_challenge(member=resolved.member, purpose=PURPOSE.PASSWORD_RESET, target_email=resolved.email)
        return None
    return request_sms_password_code(member=resolved.member, e164=resolved.e164, purpose=PURPOSE.PASSWORD_RESET)


def _reset_failure_outcome(exc: Exception):
    """Throttles, invalid numbers and a spent SMS budget sent nothing; other errors are classified."""
    from apps.authn.models import SendVerificationRequest
    from apps.authn.services.send_verification.exceptions import SendVerificationError
    from apps.authn.services.send_verification.outcomes import failure_status

    definitely_failed = (
        AuthChallengeThrottled,
        PhoneVerificationThrottled,
        PhoneVerificationInvalid,
        SendVerificationError,
    )
    if isinstance(exc, definitely_failed):
        return SendVerificationRequest.Status.DEFINITELY_FAILED
    return failure_status(exc)
