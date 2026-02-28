"""
Passwordless login via email verification code.
"""

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from authn.serializers.login_code import RequestLoginCodeSerializer, VerifyLoginCodeSerializer
from authn.throttles import LoginRateThrottle
from notify.models import VerificationRequest
from notify.services import RateLimitError, VerificationError, issue_code, verify_code


class RequestLoginCodeView(APIView):
    """
    API endpoint to request a login verification code.
    Sends a 6-digit code to the user's email.
    """

    throttle_classes = [LoginRateThrottle]

    def post(self, request):
        serializer = RequestLoginCodeSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        member = serializer.validated_data["member"]

        # Only issue code if member exists and is active; otherwise return generic message
        if member is not None:
            try:
                issue_code(
                    channel=VerificationRequest.CHANNEL_EMAIL,
                    target=member.email,
                    purpose="login",
                    code_length=6,
                    expires_in_minutes=10,
                    max_attempts=5,
                    rate_limit_per_hour=5,
                    context={"recipient_name": member.get_full_name() or member.username},
                )
            except RateLimitError:
                return Response(
                    {"error": "Too many requests. Please try again later."},
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )

        return Response(
            {"message": "If an account with this email exists, a code has been sent."},
            status=status.HTTP_200_OK,
        )


class VerifyLoginCodeView(APIView):
    """
    API endpoint to verify a login code and return JWT tokens.
    """

    throttle_classes = [LoginRateThrottle]

    def post(self, request):
        serializer = VerifyLoginCodeSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        member = serializer.validated_data["member"]
        code = serializer.validated_data["code"]

        try:
            verify_code(
                channel=VerificationRequest.CHANNEL_EMAIL,
                target=member.email,
                submitted_code=code,
                purpose="login",
            )
        except VerificationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        refresh = RefreshToken.for_user(member)

        return Response(
            {
                "message": "Login successful.",
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
