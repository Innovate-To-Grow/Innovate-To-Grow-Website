from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from ..serializers import (
    RequestCodeSerializer,
    RequestLinkSerializer,
    SendNotificationSerializer,
    VerifyCodeSerializer,
)
from ..services import (
    RateLimitError,
    VerificationError,
    issue_code,
    issue_link,
    send_notification,
    verify_code,
    verify_link,
)


class RequestCodeAPIView(APIView):
    """
    Issue and send a verification code by email or SMS.
    """

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = RequestCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            issue_code(
                channel=data["channel"],
                target=data["target"],
                purpose=data.get("purpose", "contact_verification"),
                expires_in_minutes=10,
                max_attempts=5,
                rate_limit_per_hour=5,
            )
        except RateLimitError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_429_TOO_MANY_REQUESTS)

        return Response({"detail": "Verification code sent."}, status=status.HTTP_201_CREATED)


class RequestLinkAPIView(APIView):
    """
    Issue and send a verification link by email or SMS.
    """

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = RequestLinkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            _, link = issue_link(
                channel=data["channel"],
                target=data["target"],
                purpose=data.get("purpose", "contact_verification"),
                expires_in_minutes=60,
                max_attempts=5,
                rate_limit_per_hour=5,
                base_url=data.get("base_url") or None,
            )
        except RateLimitError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_429_TOO_MANY_REQUESTS)

        return Response({"detail": "Verification link sent.", "token": link}, status=status.HTTP_201_CREATED)


class VerifyCodeAPIView(APIView):
    """
    Validate a verification code.
    """

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = VerifyCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            verify_code(
                channel=data["channel"],
                target=data["target"],
                submitted_code=data["code"],
                purpose=data.get("purpose", "contact_verification"),
            )
        except VerificationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"detail": "Verification successful."}, status=status.HTTP_200_OK)


class VerifyLinkAPIView(APIView):
    """
    Validate a verification link token.
    """

    permission_classes = [AllowAny]

    def get(self, request, token, *args, **kwargs):
        purpose = request.query_params.get("purpose", "contact_verification")
        try:
            verify_link(token=token, purpose=purpose)
        except VerificationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"detail": "Verification successful."}, status=status.HTTP_200_OK)


class SendNotificationAPIView(APIView):
    """
    Send a generic notification via email or SMS.
    """

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = SendNotificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        log = send_notification(
            channel=data["channel"],
            target=data["target"],
            subject=data.get("subject", ""),
            message=data["message"],
            provider=data.get("provider") or None,
        )

        return Response(
            {"detail": "Notification sent.", "status": log.status, "id": log.id},
            status=status.HTTP_200_OK,
        )

