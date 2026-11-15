"""Sending and checking a registration's phone code: the verification context an event grants, and the SMS calls."""

from rest_framework import status
from rest_framework.response import Response

from apps.event.models import Event


def _verification_context(event_slug: str | None) -> str | None:
    eligible = Event.objects.filter(
        registration_open=True,
        collect_phone=True,
        verify_phone=True,
    )
    if event_slug:
        event = eligible.filter(slug=event_slug).first()
        return f"event-registration:{event.pk}" if event else None

    # One-release compatibility bridge for clients predating event_slug and
    # challenge_id. The grant remains member/phone-bound and single-use, and
    # registration is the only path allowed to consume this legacy context.
    # Remove no earlier than 2026-10-23.
    if eligible.exists():
        from .phones import LEGACY_EVENT_REGISTRATION_CONTEXT

        return LEGACY_EVENT_REGISTRATION_CONTEXT
    return None


def _send_registration_code(member, phone: str, verification_context: str):
    """Start the phone challenge; the guarded send's ``(payload, status)`` or ``SendOutcome``."""
    from apps.authn.services.send_verification.guard.outcomes import SendOutcome, failure_status
    from apps.authn.services.sms import (
        PhoneNumberOptedOut,
        PhoneVerificationBusy,
        PhoneVerificationDeliveryError,
        PhoneVerificationInvalid,
        start_phone_verification,
    )

    try:
        challenge = start_phone_verification(
            phone,
            purpose="event_registration",
            member=member,
            context_identifier=verification_context,
        )
    except PhoneVerificationInvalid:
        return (
            {"detail": "Invalid phone number."},
            status.HTTP_400_BAD_REQUEST,
        )
    except PhoneNumberOptedOut as exc:
        # The number replied STOP (nothing was sent): say so, as a definite failure.
        return SendOutcome(
            {"detail": str(exc), "code": "phone_opted_out"}, status.HTTP_400_BAD_REQUEST, failure_status(exc)
        )
    except PhoneVerificationBusy as exc:
        # Held back by the delivery rate (nothing was sent): say when to ask again; the guard adds Retry-After.
        return SendOutcome(
            {"detail": str(exc), "retry_after": exc.retry_after},
            status.HTTP_503_SERVICE_UNAVAILABLE,
            failure_status(exc),
        )
    except PhoneVerificationDeliveryError as exc:
        return SendOutcome(
            {"detail": "Failed to send verification code. Please try again later."},
            status.HTTP_503_SERVICE_UNAVAILABLE,
            failure_status(exc),
            str(exc.challenge_id or ""),
        )
    return (
        {
            "detail": "Verification code sent.",
            "phone": phone,
            "challenge_id": challenge["challenge_id"],
        },
        status.HTTP_200_OK,
    )


def _verify_registration_code(member, phone: str, code: str, challenge_id, verification_context: str):
    """The verified challenge (kept for the registration submit), or the error ``Response``."""
    import apps.event.views.registration as registration_api

    try:
        from apps.authn.services.sms import (
            PhoneVerificationInvalid,
            PhoneVerificationThrottled,
            check_phone_verification,
        )

        return check_phone_verification(
            phone,
            code,
            challenge_id=challenge_id,
            purpose="event_registration",
            member=member,
            context_identifier=verification_context,
            consume=False,
        )
    except PhoneVerificationThrottled:
        return Response(
            {"detail": "Too many failed attempts. Please request a new code."},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )
    except PhoneVerificationInvalid:
        return Response(
            {"detail": "Invalid or expired verification code."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except Exception:
        registration_api.logger.warning("Phone verification failed", exc_info=True)
        return Response(
            {"detail": "Verification service is unavailable. Please try again later."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
