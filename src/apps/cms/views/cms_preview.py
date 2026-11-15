from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny, BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cms.models import CMSPage
from apps.cms.serializers.cms import CMSPageSerializer
from apps.core.utils.access import user_can_access_app

_LIVE_PREVIEW_TTL = 600  # 10 minutes


class HasCMSAppAccess(BasePermission):
    """Allow only members with admin access to the cms app.

    Mirrors the per-app gate used everywhere else (see
    apps.core.utils.access.user_can_access_app): superusers (I2G Master) and staff whose
    ``admin_apps`` includes "cms" are granted; everyone else is denied.
    """

    message = "CMS app access is required."

    def has_permission(self, request, view):
        return user_can_access_app(request.user, "cms")


class CMSPreviewFetchView(APIView):
    """Fetch cached preview data by token."""

    rate_limit_scope = "tokenized-link"

    permission_classes = [AllowAny]
    authentication_classes = []  # the token in the URL is the capability; the caller's identity is never read

    # noinspection PyMethodMayBeStatic,PyUnusedLocal
    def get(self, request, token):
        data = cache.get(f"cms:preview:{token}")
        if data is None:
            return Response({"detail": "Preview not found or expired."}, status=404)
        return Response(data)


class CMSLivePreviewView(APIView):
    """Store and retrieve live-preview page data keyed by page UUID.

    POST (cms-app only): admin JS pushes the current editor state here on every edit.
    GET  (public cache): preview tab polls this endpoint to render the latest state.
                       cms-app members may fall back to the current DB state.
    """

    rate_limit_scope = "staff-polling"

    # Session auth needed for admin JS; JWT default handles API clients.
    authentication_classes = [SessionAuthentication]

    def get_permissions(self):
        if self.request.method == "POST":
            return [HasCMSAppAccess()]
        return [AllowAny()]

    # noinspection PyMethodMayBeStatic,PyUnusedLocal
    def get(self, request, page_id):
        cached = cache.get(f"cms:live-preview:{page_id}")
        if cached is not None:
            return Response(cached)

        if not user_can_access_app(request.user, "cms"):
            return Response({"detail": "Preview not found or expired."}, status=404)

        page = CMSPage.objects.prefetch_related("blocks").filter(pk=page_id).first()
        if page is None:
            return Response({"detail": "Page not found."}, status=404)
        return Response(CMSPageSerializer(page).data)

    # noinspection PyMethodMayBeStatic
    def post(self, request, page_id):
        import json

        data = request.data
        if not isinstance(data, dict):
            return Response({"detail": "Invalid JSON."}, status=400)

        # Reject oversize payloads before they hit the cache / GET reflection.
        # 512 KB is ~10x a typical page payload and small enough that the GET
        # reflection cannot be used to blow up downstream consumers.
        try:
            serialized_size = len(json.dumps(data, default=str))
        except (TypeError, ValueError):
            return Response({"detail": "Payload is not serializable."}, status=400)
        if serialized_size > 512_000:
            return Response({"detail": "Preview payload too large."}, status=413)

        data.pop("expires_at", None)
        data["expires_at"] = (timezone.now() + timedelta(seconds=_LIVE_PREVIEW_TTL)).isoformat()
        cache.set(f"cms:live-preview:{page_id}", data, timeout=_LIVE_PREVIEW_TTL)
        return Response({"ok": True})
