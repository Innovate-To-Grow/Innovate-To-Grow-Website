"""Login-link endpoint for emailed one-click login (campaign and ticket emails).

Served at ``/mail/login-link/`` and the legacy alias ``/mail/magic-login/``
(tokens issued before the rename remain valid).
"""

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authn.throttles import LoginRateThrottle
from apps.authn.views.helpers import build_auth_success_payload
from apps.mail.models import LoginLinkToken


class LoginLinkView(APIView):
    """Exchange an emailed login-link token for JWT credentials."""

    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        token = request.data.get("token", "").strip()
        if not token:
            return Response({"detail": "Token is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            link = LoginLinkToken.objects.select_related("member", "campaign", "registration__event").get(token=token)
        except LoginLinkToken.DoesNotExist:
            return Response({"detail": "Invalid login link."}, status=status.HTTP_400_BAD_REQUEST)

        # Same generic message as an unknown token — don't reveal account state.
        if not link.member.is_active:
            return Response({"detail": "Invalid login link."}, status=status.HTTP_400_BAD_REQUEST)

        if link.is_expired:
            return Response({"detail": "This login link has expired."}, status=status.HTTP_400_BAD_REQUEST)

        if link.is_reusable:
            # Conditional on expiry so a concurrent revoke/expiry can't slip through.
            if not link.record_reusable_use():
                return Response({"detail": "This login link has expired."}, status=status.HTTP_400_BAD_REQUEST)
        elif not link.try_mark_used():
            return Response({"detail": "This login link has already been used."}, status=status.HTTP_400_BAD_REQUEST)

        payload = build_auth_success_payload(link.member, "Login successful.")
        payload["redirect_to"] = link.effective_redirect_path
        return Response(payload, status=status.HTTP_200_OK)
