import logging

from django.core.cache import cache
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from pages.models import CMSPage
from pages.serializers.cms import CMSPageSerializer

logger = logging.getLogger(__name__)


class CMSPreviewFetchView(APIView):
    """Fetch cached preview data by token."""

    permission_classes = [AllowAny]

    def get(self, request, token):
        data = cache.get(f"cms:preview:{token}")
        if data is None:
            return Response({"detail": "Preview not found or expired."}, status=404)
        return Response(data)


class CMSPageView(APIView):
    """Serve a published CMS page by its route path."""

    permission_classes = [AllowAny]

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
