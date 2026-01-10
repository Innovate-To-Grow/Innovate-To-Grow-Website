"""
Email verification view.
"""

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from notify.models import VerificationRequest
from notify.services import VerificationError, verify_link

Member = get_user_model()


class VerifyEmailView(APIView):
    """
    API endpoint for email verification.
    Activates the user account and returns JWT tokens.
    """

    def post(self, request):
        token = request.data.get("token")

        if not token:
            return Response(
                {"error": "Verification token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Verify the token using notify service
            verify_link(token=token, purpose="registration")
        except VerificationError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get the verification request to find the email
        verification = VerificationRequest.objects.filter(
            token=token,
            method=VerificationRequest.METHOD_LINK,
            purpose="registration",
        ).first()

        if not verification:
            return Response(
                {"error": "Verification record not found."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Find and activate the user
        try:
            member = Member.objects.get(email__iexact=verification.target)
        except Member.DoesNotExist:
            return Response(
                {"error": "User account not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Activate the user
        if not member.is_active:
            member.is_active = True
            member.save(update_fields=["is_active"])

        # Generate JWT tokens
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
                },
            },
            status=status.HTTP_200_OK,
        )


class ResendVerificationView(APIView):
    """
    API endpoint to resend verification email.
    """

    def post(self, request):
        from notify.services import RateLimitError, issue_link

        email = request.data.get("email")

        if not email:
            return Response(
                {"error": "Email is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            member = Member.objects.get(email__iexact=email)
        except Member.DoesNotExist:
            # Don't reveal if email exists
            return Response(
                {"message": "If an account exists with this email, a verification link has been sent."},
                status=status.HTTP_200_OK,
            )

        if member.is_active:
            return Response(
                {"message": "Account is already verified."},
                status=status.HTTP_200_OK,
            )

        try:
            base_url = request.build_absolute_uri("/verify-email")
            issue_link(
                channel=VerificationRequest.CHANNEL_EMAIL,
                target=member.email,
                purpose="registration",
                expires_in_minutes=60,
                base_url=base_url,
            )
        except RateLimitError:
            return Response(
                {"error": "Too many requests. Please try again later."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        return Response(
            {"message": "If an account exists with this email, a verification link has been sent."},
            status=status.HTTP_200_OK,
        )
