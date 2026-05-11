from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


class SendPhoneCodeView(APIView):
    """Send a verification SMS to a phone number (pre-registration, inline)."""

    permission_classes = [IsAuthenticated]

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        import event.views.registration as registration_api

        phone = request.data.get("phone", "").strip()
        region = request.data.get("region", "1-US")
        if not phone:
            return Response(
                {"detail": "Phone number is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        phone_error = registration_api._validate_phone_digits(phone, region)
        if phone_error:
            return Response({"detail": phone_error}, status=status.HTTP_400_BAD_REQUEST)

        phone = registration_api._normalize_phone(phone, region)
        try:
            from authn.services.sms import start_phone_verification
            from authn.services.sms.twilio_verify import PhoneVerificationDeliveryError, PhoneVerificationInvalid

            registration_api._clear_phone_verification(request.user, phone)
            start_phone_verification(phone)
        except PhoneVerificationInvalid:
            return Response(
                {"detail": "Invalid phone number."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except PhoneVerificationDeliveryError:
            return _sms_unavailable_response()
        except Exception:
            registration_api.logger.warning(
                "Failed to send phone verification SMS",
                exc_info=True,
            )
            return _sms_unavailable_response()

        return Response({"detail": "Verification code sent.", "phone": phone})


class VerifyPhoneCodeView(APIView):
    """Verify a phone SMS code (pre-registration, inline)."""

    permission_classes = [IsAuthenticated]

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        import event.views.registration as registration_api

        phone = request.data.get("phone", "").strip()
        code = request.data.get("code", "").strip()
        region = request.data.get("region", "1-US")
        if not phone or not code:
            return Response(
                {"detail": "Phone and code are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        phone = registration_api._normalize_phone(phone, region)
        try:
            from authn.services.sms import check_phone_verification
            from authn.services.sms.twilio_verify import PhoneVerificationInvalid, PhoneVerificationThrottled

            check_phone_verification(phone, code)
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

        registration_api._mark_phone_verified(request.user, phone)
        return Response({"detail": "Phone verified.", "phone": phone, "verified": True})


def _sms_unavailable_response():
    return Response(
        {"detail": "Failed to send verification code. Please try again later."},
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )
