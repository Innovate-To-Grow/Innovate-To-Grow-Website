from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from pages.serializers import PageViewCreateSerializer
from pages.services.analytics import enqueue


class PageViewThrottle(AnonRateThrottle):
    rate = "60/min"


class PageViewCreateView(APIView):
    """Accept page-view tracking events from the frontend."""

    permission_classes = [AllowAny]
    throttle_classes = [PageViewThrottle]

    @staticmethod
    def _get_client_ip(request):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR")

    def post(self, request, *args, **kwargs):
        serializer = PageViewCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        member = request.user if request.user.is_authenticated else None
        enqueue(
            {
                "path": serializer.validated_data["path"],
                "referrer": serializer.validated_data.get("referrer", ""),
                "ip_address": self._get_client_ip(request),
                "user_agent": request.META.get("HTTP_USER_AGENT", ""),
                "member": member,
                "session_key": getattr(request.session, "session_key", None) or "",
            }
        )
        return Response(status=status.HTTP_201_CREATED)
