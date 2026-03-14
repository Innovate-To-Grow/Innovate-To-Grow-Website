import logging

from django.core.cache import cache
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import CMSPage
from .serializers import CMSPageSerializer

logger = logging.getLogger(__name__)


class CMSPageView(APIView):
    """Retrieve a CMS page by its route path.

    GET /cms/pages/<path>/
    Query params:
        preview=true — include draft pages (staff only)
    """

    permission_classes = [AllowAny]

    def get(self, request, route_path):
        route = f"/{route_path}"
        is_preview = request.query_params.get("preview") == "true"

        # Check cache for non-preview requests
        if not is_preview:
            cache_key = f"cms:page:{route}"
            cached = cache.get(cache_key)
            if cached is not None:
                return Response(cached)

        # Build queryset
        qs = CMSPage.objects.prefetch_related("blocks")

        if is_preview and request.user.is_authenticated and request.user.is_staff:
            # Staff preview: include drafts
            page = qs.filter(route=route).exclude(status="archived").first()
        else:
            # Public: only published pages
            page = qs.filter(route=route, status="published").first()

        if not page:
            return Response({"detail": "Page not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = CMSPageSerializer(page)
        data = serializer.data

        # Cache published pages
        if not is_preview and page.status == "published":
            cache.set(f"cms:page:{route}", data, timeout=300)

        return Response(data)
