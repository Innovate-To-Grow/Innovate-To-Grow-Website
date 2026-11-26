"""Exchange an admin-issued impersonation token for JWT credentials."""

import logging

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authn.models import ImpersonationToken
from apps.core.utils.access import user_is_admin

from ...shared.responses import build_auth_success_payload, read_body_string

logger = logging.getLogger(__name__)


class ImpersonateLoginView(APIView):
    """Exchange a one-time impersonation token for JWT credentials."""

    rate_limit_scope = "auth-email-link"

    permission_classes = [AllowAny]
    # Authenticated by the one-time token in the body: a stale, expired or other-account Bearer must never 401 this.
    authentication_classes = []
    # No per-IP throttle by design: the ~384-bit, five-minute, single-use admin-issued token is the control.
    throttle_classes = []

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        token = read_body_string(request, "token")
        if not token:
            return Response({"detail": "Token is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            impersonation = ImpersonationToken.objects.select_related("member", "created_by").get(token=token)
        except ImpersonationToken.DoesNotExist:
            return Response({"detail": "Invalid impersonation link."}, status=status.HTTP_400_BAD_REQUEST)

        if not impersonation.try_mark_used():
            impersonation.refresh_from_db(fields=["is_used", "expires_at"])
            detail = (
                "This impersonation link has already been used."
                if impersonation.is_used
                else "This impersonation link has expired."
            )
            return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)

        # Checked again at redemption, not only when the link was issued: the link is spent either way, and it never
        # signs in as an account that has since become an Admin, nor works once its issuer is no longer an Admin.
        if impersonation.member.is_staff or not user_is_admin(impersonation.created_by):
            logger.warning("Refused impersonation token %s: target is an Admin or issuer is not", impersonation.pk)
            return Response({"detail": "Invalid impersonation link."}, status=status.HTTP_400_BAD_REQUEST)

        logger.info(
            "Admin %s (%s) impersonated member %s (%s)",
            impersonation.created_by.id,
            impersonation.created_by.get_primary_email(),
            impersonation.member.id,
            impersonation.member.get_primary_email(),
        )

        payload = build_auth_success_payload(impersonation.member, "Impersonation login successful.")
        return Response(payload, status=status.HTTP_200_OK)
