from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from cms.serializers import PageViewCreateSerializer
from cms.services.analytics import enqueue


class PageViewThrottle(AnonRateThrottle):
    rate = "60/min"


class PageViewCreateView(APIView):
    """Accept page-view tracking events from the frontend."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [AllowAny]
    throttle_classes = [PageViewThrottle]

    @staticmethod
    def _get_client_ip(request):
        """Return the originating client IP, honouring NUM_PROXIES trusted hops.

        X-Forwarded-For is a comma-separated list appended-to by each proxy.
        With ``NUM_PROXIES = N``, the rightmost N entries are trusted proxy
        hops; the Nth-from-right entry is the actual client. If NUM_PROXIES
        is not configured (dev / tests), fall back to the leftmost entry.
        """
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded:
            parts = [p.strip() for p in forwarded.split(",") if p.strip()]
            if parts:
                num_proxies = getattr(settings, "NUM_PROXIES", None)
                if num_proxies:
                    index = max(0, len(parts) - num_proxies)
                    return parts[index]
                return parts[0]
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
