"""
Registration view for user signup.
"""

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from authn.serializers import RegisterSerializer
from notify.models import VerificationRequest
from notify.services import RateLimitError, issue_code


class RegisterView(APIView):
    """
    API endpoint for user registration.
    Creates an inactive user and sends verification code via email.
    """

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Create the user (inactive until email verified)
        member = serializer.save()

        # Generate verification code using notify service
        try:
            issue_code(
                channel=VerificationRequest.CHANNEL_EMAIL,
                target=member.email,
                purpose="registration",
                code_length=6,
                expires_in_minutes=10,
                max_attempts=5,
                rate_limit_per_hour=5,
                context={"recipient_name": member.get_full_name() or member.username},
            )
        except RateLimitError:
            # User created but rate limited - they can request new code later
            return Response(
                {
                    "message": "Account created. Too many verification requests. Please try again later.",
                    "email": member.email,
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        return Response(
            {
                "message": "Registration successful. Please check your email for the verification code.",
                "email": member.email,
            },
            status=status.HTTP_201_CREATED,
        )
