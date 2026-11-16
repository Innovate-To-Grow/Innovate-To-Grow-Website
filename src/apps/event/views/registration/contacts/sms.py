from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.event.throttles import PhoneCodeRequestThrottle, PhoneCodeVerifyThrottle

from .sms_codes import (
    _send_registration_code,
    _verification_context,
    _verify_registration_code,
)


class SendPhoneCodeView(APIView):
    """Send a verification SMS to a phone number (pre-registration, inline)."""

    rate_limit_scope = "auth-code-send"

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
        from apps.authn.services.send_verification.rules.constants import KIND_PHONE, SMS_CHANNEL

        return guarded_send(
            request,
            operation=OP_EVENT_SEND_PHONE_CODE,
            destination_kind=KIND_PHONE,
            destination_normalized=phone,
            fingerprint=fingerprint_payload({"phone": phone, "event": verification_context}),
            channel=SMS_CHANNEL,
            perform=lambda: _send_registration_code(request.user, phone, verification_context),
        )


class VerifyPhoneCodeView(APIView):
    """Verify a phone SMS code (pre-registration, inline)."""

    rate_limit_scope = "auth-code-verify"

    permission_classes = [IsAuthenticated]
    throttle_classes = [PhoneCodeVerifyThrottle]

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
        challenge = _verify_registration_code(request.user, phone, code, challenge_id, verification_context)
        if isinstance(challenge, Response):
            return challenge
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
