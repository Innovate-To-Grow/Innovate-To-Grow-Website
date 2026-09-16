from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.event.models import Event
from apps.event.throttles import PhoneCodeRequestThrottle


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


class SendPhoneCodeView(APIView):
    """Send a verification SMS to a phone number (pre-registration, inline)."""

    permission_classes = [IsAuthenticated]
    # Each send spends AWS SNS budget on a caller-supplied destination; bound
    # per-actor abuse (the service cap is per-number and rotation bypasses it).
    throttle_classes = [PhoneCodeRequestThrottle]

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        import apps.event.views.registration as registration_api

        phone = request.data.get("phone", "").strip()
        verification_context = _verification_context(request.data.get("event_slug"))
        # US-only: AWS SNS only delivers to US numbers; ignore any client-supplied region.
        region = "1-US"
        if verification_context is None:
            return Response(
                {"detail": "An open event requiring phone verification is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not phone:
            return Response(
                {"detail": "Phone number is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        phone_error = registration_api._validate_phone_digits(phone, region)
        if phone_error:
            return Response({"detail": phone_error}, status=status.HTTP_400_BAD_REQUEST)

        phone = registration_api._normalize_phone(phone, region)
        from apps.authn.services.send_verification import OP_EVENT_SEND_PHONE_CODE, fingerprint_payload, guarded_send
        from apps.authn.services.send_verification.constants import KIND_PHONE, SMS_CHANNEL
        from apps.authn.services.send_verification.outcomes import SendOutcome, failure_status
        from apps.authn.services.sms import (
            PhoneVerificationDeliveryError,
            PhoneVerificationInvalid,
            start_phone_verification,
        )

        def perform():
            try:
                challenge = start_phone_verification(
                    phone,
                    purpose="event_registration",
                    member=request.user,
                    context_identifier=verification_context,
                )
            except PhoneVerificationInvalid:
                return (
                    {"detail": "Invalid phone number."},
                    status.HTTP_400_BAD_REQUEST,
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

        return guarded_send(
            request,
            operation=OP_EVENT_SEND_PHONE_CODE,
            destination_kind=KIND_PHONE,
            destination_normalized=phone,
            fingerprint=fingerprint_payload({"phone": phone, "event": verification_context}),
            channel=SMS_CHANNEL,
            perform=perform,
        )


class VerifyPhoneCodeView(APIView):
    """Verify a phone SMS code (pre-registration, inline)."""

    permission_classes = [IsAuthenticated]

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        import apps.event.views.registration as registration_api

        phone = request.data.get("phone", "").strip()
        code = request.data.get("code", "").strip()
        challenge_id = request.data.get("challenge_id")
        verification_context = _verification_context(request.data.get("event_slug"))
        # US-only: ignore any client-supplied region so the durable challenge's
        # E.164 number matches the send path.
        region = "1-US"
        if verification_context is None:
            return Response(
                {"detail": "An open event requiring phone verification is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not phone or not code:
            return Response(
                {"detail": "Phone and code are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        phone = registration_api._normalize_phone(phone, region)
        try:
            from apps.authn.services.sms import (
                PhoneVerificationInvalid,
                PhoneVerificationThrottled,
                check_phone_verification,
            )

            challenge = check_phone_verification(
                phone,
                code,
                challenge_id=challenge_id,
                purpose="event_registration",
                member=request.user,
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

        return Response(
            {
                "detail": "Phone verified.",
                "phone": phone,
                "verified": True,
                "challenge_id": str(challenge.pk),
            }
        )


def _sms_unavailable_response():
    return Response(
        {"detail": "Failed to send verification code. Please try again later."},
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )
