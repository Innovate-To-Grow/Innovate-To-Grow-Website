"""Views for public email-code auth flows."""

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from authn.serializers import (
    LoginCodeRequestSerializer,
    LoginCodeVerifySerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    PasswordResetVerifySerializer,
    RegisterResendCodeSerializer,
    RegisterVerifyCodeSerializer,
    UnifiedEmailAuthRequestSerializer,
    UnifiedEmailAuthVerifySerializer,
)
from authn.services import consume_login_or_registration_challenge
from authn.throttles import EmailCodeRequestThrottle, EmailCodeVerifyThrottle

from ..helpers import build_auth_success_payload
from .email_code_helpers import auth_challenge_response, request_code_response


class LoginCodeRequestView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [EmailCodeRequestThrottle]

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        return request_code_response(request, LoginCodeRequestSerializer)


class EmailAuthRequestCodeView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [EmailCodeRequestThrottle]

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        return request_code_response(request, UnifiedEmailAuthRequestSerializer)


class LoginCodeVerifyView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [EmailCodeVerifyThrottle]

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        serializer = LoginCodeVerifySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        challenge = serializer.validated_data["challenge"]
        if not challenge.member.is_active:
            return Response(
                {"detail": "Verification code is invalid or has expired."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        _mark_contact_email_verified(challenge.member, challenge.target_email)
        consume_login_or_registration_challenge(challenge)
        return Response(
            build_auth_success_payload(challenge.member, "Login successful."),
            status=status.HTTP_200_OK,
        )


class EmailAuthVerifyCodeView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [EmailCodeVerifyThrottle]

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        serializer = UnifiedEmailAuthVerifySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        challenge = serializer.validated_data["challenge"]
        member = challenge.member
        flow = serializer.validated_data["flow"]

        if flow == "register" and not member.is_active:
            member.is_active = True
            member.save(update_fields=["is_active"])
            _link_email_subscriber(member)
        elif flow == "login" and not member.is_active:
            return Response(
                {"detail": "Verification code is invalid or has expired."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        _mark_contact_email_verified(member, challenge.target_email)
        consume_login_or_registration_challenge(challenge)
        return Response(
            build_auth_success_payload(
                member,
                "Login successful." if flow == "login" else "Email verified. Registration successful.",
            ),
            status=status.HTTP_200_OK,
        )


class RegisterVerifyCodeView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [EmailCodeVerifyThrottle]

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        serializer = RegisterVerifyCodeSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        challenge = serializer.validated_data["challenge"]
        member = challenge.member
        if not member.is_active:
            member.is_active = True
            member.save(update_fields=["is_active"])
            _link_email_subscriber(member)
        _mark_contact_email_verified(member, challenge.target_email)
        consume_login_or_registration_challenge(challenge)
        return Response(
            build_auth_success_payload(member, "Email verified. Registration successful."),
            status=status.HTTP_200_OK,
        )


class RegisterResendCodeView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [EmailCodeRequestThrottle]

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        return request_code_response(request, RegisterResendCodeSerializer)


class PasswordResetRequestView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [EmailCodeRequestThrottle]

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        return request_code_response(request, PasswordResetRequestSerializer)


class PasswordResetVerifyView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [EmailCodeVerifyThrottle]

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        return auth_challenge_response(request, PasswordResetVerifySerializer)


class PasswordResetConfirmView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [EmailCodeVerifyThrottle]

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        return auth_challenge_response(request, PasswordResetConfirmSerializer)


def _link_email_subscriber(member):
    """Link anonymous ContactEmail records to a newly activated member."""
    from authn.models import ContactEmail

    primary_email = member.get_primary_email()
    if primary_email:
        ContactEmail.objects.filter(
            email_address__iexact=primary_email,
            member__isnull=True,
        ).update(member=member)


def _mark_contact_email_verified(member, email_address):
    """Mark the member's ContactEmail as verified after successful code verification."""
    from authn.models import ContactEmail

    ContactEmail.objects.filter(
        member=member,
        email_address__iexact=email_address,
        verified=False,
    ).update(verified=True)
