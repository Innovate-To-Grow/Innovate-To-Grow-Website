"""Password reset by a code sent by email or SMS.

Like the other email-code views, these are not throttled per client IP, with one exception: a password reset requested
for a PHONE number, which sends an SMS, takes the per-IP SMS throttle, but only as a fallback while no global SMS daily
budget is configured.

That budget is reserved where the SMS is dispatched (``start_phone_verification``), so a reset for a number without
an account costs nothing, and a spent budget never changes the reset's answer: it stays the neutral 202 for every
number and the SMS is simply not sent (``PasswordResetRequestSerializer.save``).
"""

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authn.security.throttles import sms_request_throttles
from apps.authn.serializers import (
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    PasswordResetVerifySerializer,
)
from apps.authn.services.send_verification import (
    OP_PASSWORD_RESET_REQUEST_CODE,
)
from apps.authn.services.send_verification.rules.constants import EMAIL_CHANNEL, KIND_PHONE, SMS_CHANNEL

from ...shared.code_requests import auth_challenge_response, protected_save


class PasswordResetRequestView(APIView):
    rate_limit_scope = "auth-code-send"
    authentication_classes = []
    permission_classes = [AllowAny]

    def get_throttles(self):
        # Only a phone identifier triggers an SMS send (real money), so only it can take the per-IP SMS throttle,
        # and only as a fallback while no global SMS daily budget is configured (``sms_request_throttles``). An
        # email identifier is never throttled per IP (campus NAT); the per-destination cooldown and hourly cap bound
        # it. The channel is inferred from the identifier before the view body runs.
        data = self.request.data if isinstance(self.request.data, dict) else {}
        # Pick the identifier exactly as PasswordResetRequestSerializer does: each field is trimmed BEFORE the
        # ``identifier`` -> ``email`` fallback. Deciding from the untrimmed value would let a blank ``identifier``
        # plus a phone number in the ``email`` alias send an SMS while skipping this throttle.
        identifier = str(data.get("identifier") or "").strip() or str(data.get("email") or "").strip()
        if identifier and "@" not in identifier and any(ch.isdigit() for ch in identifier):
            return sms_request_throttles()
        return []

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        destination_kind = serializer.validated_data["destination_kind"]
        destination = serializer.validated_data["destination_normalized"]
        channel = SMS_CHANNEL if destination_kind == KIND_PHONE else EMAIL_CHANNEL
        return protected_save(
            request,
            serializer,
            operation=OP_PASSWORD_RESET_REQUEST_CODE,
            destination_kind=destination_kind,
            destination=destination,
            fingerprint={"identifier": destination, "kind": destination_kind},
            channel=channel,
        )


class PasswordResetVerifyView(APIView):
    rate_limit_scope = "auth-code-verify"
    authentication_classes = []
    permission_classes = [AllowAny]

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        return auth_challenge_response(request, PasswordResetVerifySerializer)


class PasswordResetConfirmView(APIView):
    rate_limit_scope = "auth-code-verify"
    authentication_classes = []
    permission_classes = [AllowAny]

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        return auth_challenge_response(request, PasswordResetConfirmSerializer)
