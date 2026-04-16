import logging
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from cms.models import CMSPage
from cms.serializers.cms import CMSPageSerializer

logger = logging.getLogger(__name__)

_LIVE_PREVIEW_TTL = 600  # 10 minutes


class CMSPreviewFetchView(APIView):
    """Fetch cached preview data by token."""

    permission_classes = [AllowAny]

    # noinspection PyMethodMayBeStatic,PyUnusedLocal
    def get(self, request, token):
        data = cache.get(f"cms:preview:{token}")
        if data is None:
            return Response({"detail": "Preview not found or expired."}, status=404)
        return Response(data)


class CMSLivePreviewView(APIView):
    """Store and retrieve live-preview page data keyed by page UUID.

    POST (staff-only): admin JS pushes the current editor state here on every edit.
    GET  (public cache): preview tab polls this endpoint to render the latest state.
                       Staff users may fall back to the current DB state.
    """

    # Session auth needed for admin JS; JWT default handles API clients.
    authentication_classes = [SessionAuthentication]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAdminUser()]
        return [AllowAny()]

    # noinspection PyMethodMayBeStatic,PyUnusedLocal
    def get(self, request, page_id):
        cached = cache.get(f"cms:live-preview:{page_id}")
        if cached is not None:
            return Response(cached)

        if not request.user.is_authenticated or not request.user.is_staff:
            return Response({"detail": "Preview not found or expired."}, status=404)

        page = CMSPage.objects.prefetch_related("blocks").filter(pk=page_id).first()
        if page is None:
            return Response({"detail": "Page not found."}, status=404)
        return Response(CMSPageSerializer(page).data)

    # noinspection PyMethodMayBeStatic
    def post(self, request, page_id):
        data = request.data
        if not isinstance(data, dict):
            return Response({"detail": "Invalid JSON."}, status=400)

        data.pop("expires_at", None)
        data["expires_at"] = (timezone.now() + timedelta(seconds=_LIVE_PREVIEW_TTL)).isoformat()
        cache.set(f"cms:live-preview:{page_id}", data, timeout=_LIVE_PREVIEW_TTL)
        return Response({"ok": True})


class CMSPageView(APIView):
    """Serve a published CMS page by its route path."""

    permission_classes = [AllowAny]

    # noinspection PyMethodMayBeStatic
    def get(self, request, route_path=""):
        route = f"/{route_path}" if route_path else "/"
        is_preview = request.query_params.get("preview") == "true"

        if not is_preview:
            cached = cache.get(f"cms:page:{route}")
            if cached is not None:
                return Response(cached)

        qs = CMSPage.objects.prefetch_related("blocks")
        if is_preview and request.user.is_authenticated and request.user.is_staff:
            qs = qs.filter(route=route).exclude(status="archived")
        else:
            qs = qs.filter(route=route, status="published")

        page = qs.first()
        if page is None:
            return Response({"detail": "Page not found."}, status=404)

        data = CMSPageSerializer(page).data

        if not is_preview:
            cache.set(f"cms:page:{route}", data, timeout=300)

        return Response(data)
