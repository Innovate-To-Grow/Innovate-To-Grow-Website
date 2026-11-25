from rest_framework.response import Response

from ..auth.throttles import CliReadThrottle
from .base import AdminAPIView


class WhoAmIView(AdminAPIView):
    rate_limit_scope = "cli"
    throttle_classes = [CliReadThrottle]

    def get(self, request):
        member = request.user
        token = request.auth
        return Response(
            {
                "member_uuid": str(member.pk),
                "name": member.get_full_name() or member.get_username(),
                "email": member.get_primary_email(),
                "is_staff": member.is_staff,
                "is_active": member.is_active,
                # Deprecated compatibility key: there is one Admin role, so it always equals is_staff. CLI clients
                # released since 2026-08-05 show every app only when it is true. Computed, not read from the
                # mirrored column.
                "is_superuser": bool(member.is_staff),
                "token_expires_at": token.expires_at.isoformat(),
            }
        )
