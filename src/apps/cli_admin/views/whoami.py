from rest_framework.response import Response

from ..throttles import CliReadThrottle
from .base import AdminAPIView


class WhoAmIView(AdminAPIView):
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
                "is_superuser": member.is_superuser,
                "token_expires_at": token.expires_at.isoformat(),
            }
        )
