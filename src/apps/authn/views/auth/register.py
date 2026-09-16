"""
Registration view for user signup.
"""

from django.utils.crypto import salted_hmac
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authn.security.throttles import EmailCodeRequestThrottle
from apps.authn.serializers import RegisterSerializer
from apps.authn.services.send_verification import OP_REGISTER, fingerprint_payload, guarded_send
from apps.authn.services.send_verification.constants import EMAIL_CHANNEL, KIND_EMAIL


class RegisterView(APIView):
    """
    API endpoint for user registration.
    Creates or updates an inactive user and sends a verification code.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [EmailCodeRequestThrottle]

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data["email"]
        return guarded_send(
            request,
            operation=OP_REGISTER,
            destination_kind=KIND_EMAIL,
            destination_normalized=email,
            fingerprint=fingerprint_payload(
                {
                    "email": email,
                    "first_name": serializer.validated_data.get("first_name", ""),
                    "last_name": serializer.validated_data.get("last_name", ""),
                    "organization": serializer.validated_data.get("organization", ""),
                    "title": serializer.validated_data.get("title", ""),
                    "password_digest": salted_hmac(
                        "send-verification.register.password",
                        serializer.validated_data["_decrypted_password"],
                        algorithm="sha256",
                    ).hexdigest(),
                }
            ),
            channel=EMAIL_CHANNEL,
            perform=_register_payload(serializer),
        )


def _register_payload(serializer):
    def perform():
        serializer.save()
        return (
            {
                "message": "Registration started. Check your email for a verification code.",
                "next_step": "verify_code",
            },
            status.HTTP_202_ACCEPTED,
        )

    return perform
