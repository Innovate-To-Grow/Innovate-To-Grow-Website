"""Challenge issuance and send-request status for protected verification-code sends."""

from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authn.security.throttles import SendVerificationChallengeThrottle, SendVerificationStatusThrottle
from apps.authn.services.send_verification import (
    ALL_OPERATIONS,
    SendVerificationError,
    issue_challenge,
    lookup_request,
    serialize_challenge,
    serialize_request_status,
    verification_error_response,
)
from apps.authn.services.send_verification.destinations import resolve_operation_destination
from apps.authn.services.send_verification.principal import authenticate_for_operation


@method_decorator(never_cache, name="dispatch")
class SendVerificationChallengeView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [SendVerificationChallengeThrottle]
    allowed_operations = frozenset(operation for operation in ALL_OPERATIONS if not operation.startswith("admin."))

    def get_authenticate_header(self, request):
        return "Bearer"

    def post(self, request):
        data = request.data if isinstance(request.data, dict) else {}
        operation = str(data.get("operation") or "").strip()
        if operation not in self.allowed_operations:
            return Response({"operation": ["Unknown operation."]}, status=status.HTTP_400_BAD_REQUEST)
        authenticate_for_operation(request, operation)
        try:
            destination_kind, destination = resolve_operation_destination(
                request,
                operation=operation,
                data=data,
            )
        except PermissionDenied:
            return Response(
                {"detail": "Authentication credentials were not provided."}, status=status.HTTP_401_UNAUTHORIZED
            )
        except ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
        except SendVerificationError as exc:
            return verification_error_response(exc)

        try:
            row, config, challenge_dict = issue_challenge(
                request,
                operation=operation,
                destination_kind=destination_kind,
                destination_normalized=destination,
            )
        except SendVerificationError as exc:
            return verification_error_response(exc)

        response = Response(serialize_challenge(row, config, challenge_dict), status=status.HTTP_200_OK)
        response["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response["Pragma"] = "no-cache"
        return response


@method_decorator(never_cache, name="dispatch")
class SendVerificationRequestStatusView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [SendVerificationStatusThrottle]

    def get_authenticate_header(self, request):
        return "Bearer"

    def get(self, request, request_id):
        try:
            record = lookup_request(request, request_id)
        except SendVerificationError as exc:
            return verification_error_response(exc)
        response = Response(serialize_request_status(record), status=status.HTTP_200_OK)
        response["Cache-Control"] = "no-store"
        return response
