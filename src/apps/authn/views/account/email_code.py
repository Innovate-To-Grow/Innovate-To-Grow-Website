"""
Views for authenticated email-code account flows.
"""
# noinspection DuplicatedCode

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authn.constants import VERIFICATION_LINK_INVALID
from apps.authn.security.throttles import (
    EmailCodeUserRequestThrottle,
    EmailCodeVerifyThrottle,
    PhoneCodeRequestThrottle,
)
from apps.authn.serializers import (
    AccountEmailsSerializer,
    ChangePasswordCodeConfirmSerializer,
    ChangePasswordCodeRequestSerializer,
    ChangePasswordCodeVerifySerializer,
    DeleteAccountCodeConfirmSerializer,
    DeleteAccountCodeRequestSerializer,
    DeleteAccountCodeVerifySerializer,
)
from apps.authn.services import AuthChallengeInvalid
from apps.authn.services.send_verification import OP_CHANGE_PASSWORD_REQUEST_CODE, OP_DELETE_ACCOUNT_REQUEST_CODE
from apps.authn.services.send_verification.constants import EMAIL_CHANNEL, KIND_EMAIL, KIND_PHONE, SMS_CHANNEL

from ..auth.email_code_helpers import protected_save


class AccountEmailsView(APIView):
    permission_classes = [IsAuthenticated]

    # noinspection PyMethodMayBeStatic
    def get(self, request):
        serializer = AccountEmailsSerializer(instance=request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ChangePasswordCodeRequestView(APIView):
    permission_classes = [IsAuthenticated]
    # Per-user caps on both the email send budget and the SMS send budget — the
    # channel isn't known until the serializer runs, so apply both (equal 5/min
    # scopes). The SMS service also enforces a per-number hourly send cap.
    throttle_classes = [EmailCodeUserRequestThrottle, PhoneCodeRequestThrottle]

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        serializer = ChangePasswordCodeRequestSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        selected = serializer.validated_data["selected"]
        destination_kind = KIND_PHONE if selected.channel == SMS_CHANNEL else KIND_EMAIL
        destination = selected.e164 if destination_kind == KIND_PHONE else selected.target_email
        channel = SMS_CHANNEL if destination_kind == KIND_PHONE else EMAIL_CHANNEL
        return protected_save(
            request,
            serializer,
            operation=OP_CHANGE_PASSWORD_REQUEST_CODE,
            destination_kind=destination_kind,
            destination=destination,
            fingerprint={"destination": destination, "kind": destination_kind},
            channel=channel,
        )


class ChangePasswordCodeVerifyView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [EmailCodeVerifyThrottle]

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        serializer = ChangePasswordCodeVerifySerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        payload = serializer.save()
        return Response(payload, status=status.HTTP_200_OK)


class ChangePasswordCodeConfirmView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [EmailCodeVerifyThrottle]

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        serializer = ChangePasswordCodeConfirmSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            payload = serializer.save()
        except AuthChallengeInvalid:
            return Response({"detail": VERIFICATION_LINK_INVALID}, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload, status=status.HTTP_200_OK)


class DeleteAccountCodeRequestView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [EmailCodeUserRequestThrottle]

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        serializer = DeleteAccountCodeRequestSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        destination = serializer.validated_data["target_email"]
        return protected_save(
            request,
            serializer,
            operation=OP_DELETE_ACCOUNT_REQUEST_CODE,
            destination_kind=KIND_EMAIL,
            destination=destination,
            fingerprint={"email": destination},
            channel=EMAIL_CHANNEL,
        )


class DeleteAccountCodeVerifyView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [EmailCodeVerifyThrottle]

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        serializer = DeleteAccountCodeVerifySerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        payload = serializer.save()
        return Response(payload, status=status.HTTP_200_OK)


class DeleteAccountCodeConfirmView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [EmailCodeVerifyThrottle]

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        serializer = DeleteAccountCodeConfirmSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            payload = serializer.save()
        except AuthChallengeInvalid:
            return Response({"detail": VERIFICATION_LINK_INVALID}, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload, status=status.HTTP_200_OK)
