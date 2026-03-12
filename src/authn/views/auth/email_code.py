"""
Views for public email-code auth flows.
"""

from rest_framework import serializers, status
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
from authn.services import AuthChallengeInvalid, consume_login_or_registration_challenge
from authn.throttles import EmailCodeRequestThrottle, EmailCodeVerifyThrottle

from ..helpers import build_auth_success_payload, challenge_error_response


class LoginCodeRequestView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [EmailCodeRequestThrottle]

    def post(self, request):
        serializer = LoginCodeRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            payload = serializer.save()
        except serializers.ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:  # noqa: BLE001
            return challenge_error_response(exc)
        return Response(payload, status=status.HTTP_202_ACCEPTED)


class EmailAuthRequestCodeView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [EmailCodeRequestThrottle]

    def post(self, request):
        serializer = UnifiedEmailAuthRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            payload = serializer.save()
        except serializers.ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:  # noqa: BLE001
            return challenge_error_response(exc)
        return Response(payload, status=status.HTTP_202_ACCEPTED)


class LoginCodeVerifyView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [EmailCodeVerifyThrottle]

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

        consume_login_or_registration_challenge(challenge)
        return Response(
            build_auth_success_payload(challenge.member, "Login successful."),
            status=status.HTTP_200_OK,
        )


class EmailAuthVerifyCodeView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [EmailCodeVerifyThrottle]

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
        elif flow == "login" and not member.is_active:
            return Response(
                {"detail": "Verification code is invalid or has expired."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        consume_login_or_registration_challenge(challenge)
        return Response(
            build_auth_success_payload(
                member,
                "Login successful." if flow == "login" else "Email verified. Registration successful.",
                next_step="account" if flow == "login" else "complete_profile",
                requires_profile_completion=flow == "register",
            ),
            status=status.HTTP_200_OK,
        )


class RegisterVerifyCodeView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [EmailCodeVerifyThrottle]

    def post(self, request):
        serializer = RegisterVerifyCodeSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        challenge = serializer.validated_data["challenge"]
        member = challenge.member
        if not member.is_active:
            member.is_active = True
            member.save(update_fields=["is_active"])
        consume_login_or_registration_challenge(challenge)
        return Response(
            build_auth_success_payload(member, "Email verified. Registration successful."),
            status=status.HTTP_200_OK,
        )


class RegisterResendCodeView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [EmailCodeRequestThrottle]

    def post(self, request):
        serializer = RegisterResendCodeSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            payload = serializer.save()
        except serializers.ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:  # noqa: BLE001
            return challenge_error_response(exc)
        return Response(payload, status=status.HTTP_202_ACCEPTED)


class PasswordResetRequestView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [EmailCodeRequestThrottle]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            payload = serializer.save()
        except serializers.ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:  # noqa: BLE001
            return challenge_error_response(exc)
        return Response(payload, status=status.HTTP_202_ACCEPTED)


class PasswordResetVerifyView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [EmailCodeVerifyThrottle]

    def post(self, request):
        serializer = PasswordResetVerifySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            payload = serializer.save()
        except AuthChallengeInvalid as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload, status=status.HTTP_200_OK)


class PasswordResetConfirmView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [EmailCodeVerifyThrottle]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            payload = serializer.save()
        except AuthChallengeInvalid as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload, status=status.HTTP_200_OK)
