"""
Code-based email verification for registration.
"""

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from authn.serializers.verify_code import VerifyEmailCodeSerializer
from authn.throttles import VerifyRateThrottle
from notify.models import VerificationRequest
from notify.services import VerificationError, verify_code


class VerifyEmailCodeView(APIView):
    """
    API endpoint for code-based email verification.
    Activates the user account and returns JWT tokens.
    """

    throttle_classes = [VerifyRateThrottle]

    def post(self, request):
        serializer = VerifyEmailCodeSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        member = serializer.validated_data["member"]
        code = serializer.validated_data["code"]

        try:
            verify_code(
                channel=VerificationRequest.CHANNEL_EMAIL,
                target=member.email,
                submitted_code=code,
                purpose="registration",
            )
        except VerificationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        if not member.is_active:
            member.is_active = True
            member.save(update_fields=["is_active"])

        refresh = RefreshToken.for_user(member)

        return Response(
            {
                "message": "Email verified successfully.",
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": {
                    "member_uuid": str(member.member_uuid),
                    "email": member.email,
                    "username": member.username,
                    "display_name": member.get_full_name() or member.username,
                },
            },
            status=status.HTTP_200_OK,
        )
