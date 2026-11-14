"""The registration code: check it, or send it again (not throttled per client IP: see ``email_code``)."""

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authn.serializers import (
    RegisterResendCodeSerializer,
    RegisterVerifyCodeSerializer,
)
from apps.authn.services.send_verification import (
    OP_REGISTER_RESEND_CODE,
)
from apps.authn.services.send_verification.constants import EMAIL_CHANNEL, KIND_EMAIL

from ...shared.code_requests import protected_save
from .completion import _complete_registration


class RegisterVerifyCodeView(APIView):
    rate_limit_scope = "auth-code-verify"
    authentication_classes = []
    permission_classes = [AllowAny]

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        serializer = RegisterVerifyCodeSerializer(
            data=request.data,
            context={"approved_callback": _complete_registration},
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            serializer.validated_data["approved_result"],
            status=status.HTTP_200_OK,
        )


class RegisterResendCodeView(APIView):
    rate_limit_scope = "auth-code-send"
    authentication_classes = []
    permission_classes = [AllowAny]

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        serializer = RegisterResendCodeSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        email = serializer.validated_data["email"]
        return protected_save(
            request,
            serializer,
            operation=OP_REGISTER_RESEND_CODE,
            destination_kind=KIND_EMAIL,
            destination=email,
            fingerprint={"email": email},
            channel=EMAIL_CHANNEL,
        )
