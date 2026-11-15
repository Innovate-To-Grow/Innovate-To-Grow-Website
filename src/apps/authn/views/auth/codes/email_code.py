"""Sign in, or sign up, with a code sent by email.

None of the email-code views (these, ``registration`` and ``password_reset``) is throttled per client IP (campus users
share one public address). Code requests are bounded by the ALTCHA proof plus the per-destination cooldown and hourly
cap; verification by the per-challenge attempt limit.
"""

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authn.serializers import (
    LoginCodeRequestSerializer,
    LoginCodeVerifySerializer,
    UnifiedEmailAuthRequestSerializer,
    UnifiedEmailAuthVerifySerializer,
)
from apps.authn.services.send_verification import (
    OP_EMAIL_AUTH_REQUEST_CODE,
    OP_LOGIN_REQUEST_CODE,
)
from apps.authn.services.send_verification.rules.constants import EMAIL_CHANNEL, KIND_EMAIL

from ...shared.code_requests import protected_save
from .completion import _complete_login, _complete_unified_auth


class LoginCodeRequestView(APIView):
    rate_limit_scope = "auth-code-send"
    authentication_classes = []
    permission_classes = [AllowAny]

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        serializer = LoginCodeRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        email = serializer.validated_data["email"]
        return protected_save(
            request,
            serializer,
            operation=OP_LOGIN_REQUEST_CODE,
            destination_kind=KIND_EMAIL,
            destination=email,
            fingerprint={"email": email},
            channel=EMAIL_CHANNEL,
        )


class EmailAuthRequestCodeView(APIView):
    rate_limit_scope = "auth-code-send"
    authentication_classes = []
    permission_classes = [AllowAny]

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        serializer = UnifiedEmailAuthRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        email = serializer.validated_data["email"]
        return protected_save(
            request,
            serializer,
            operation=OP_EMAIL_AUTH_REQUEST_CODE,
            destination_kind=KIND_EMAIL,
            destination=email,
            fingerprint={
                "email": email,
                "source": serializer.validated_data.get("source", "login"),
                "event": serializer.validated_data.get("event", ""),
            },
            channel=EMAIL_CHANNEL,
        )


class LoginCodeVerifyView(APIView):
    rate_limit_scope = "auth-code-verify"
    authentication_classes = []
    permission_classes = [AllowAny]

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        serializer = LoginCodeVerifySerializer(
            data=request.data,
            context={"approved_callback": _complete_login},
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            serializer.validated_data["approved_result"],
            status=status.HTTP_200_OK,
        )


class EmailAuthVerifyCodeView(APIView):
    rate_limit_scope = "auth-code-verify"
    authentication_classes = []
    permission_classes = [AllowAny]

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        serializer = UnifiedEmailAuthVerifySerializer(
            data=request.data,
            context={"approved_callback": _complete_unified_auth},
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            serializer.validated_data["approved_result"],
            status=status.HTTP_200_OK,
        )
