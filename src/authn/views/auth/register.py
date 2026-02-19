"""
Registration view for user signup.
"""

from django.conf import settings
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from authn.serializers import RegisterSerializer
from notify.models import VerificationRequest
from notify.services import RateLimitError, issue_link


class RegisterView(APIView):
    """
    API endpoint for user registration.
    Creates an inactive user and sends verification email.
    """

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Create the user (inactive until email verified)
        member = serializer.save()

        # Generate verification link using notify service
        try:
            base_url = request.build_absolute_uri("/verify-email")
            verification, link = issue_link(
                channel=VerificationRequest.CHANNEL_EMAIL,
                target=member.email,
                purpose="registration",
                expires_in_minutes=60,
                base_url=base_url,
            )
        except RateLimitError:
            # User created but rate limited - they can request new link later
            return Response(
                {
                    "message": "Account created. Too many verification requests. Please try again later.",
                    "email": member.email,
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        return Response(
            {
                "message": "Registration successful. Please check your email to verify your account.",
                "email": member.email,
                # Include token in dev mode for testing (remove in production)
                "verification_token": verification.token if settings.DEBUG else None,
            },
            status=status.HTTP_201_CREATED,
        )
