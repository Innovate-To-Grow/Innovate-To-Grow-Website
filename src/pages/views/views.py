import logging

from django.core.cache import cache
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import FooterContent, Menu, SiteSettings
from ..serializers import (
    FooterContentSerializer,
    MenuSerializer,
)

logger = logging.getLogger(__name__)


class LayoutAPIView(APIView):
    """Unified endpoint for layout data (menus and footer) with caching."""

    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        cache_key = "layout:data"

        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return Response(cached_data)

        menus = Menu.objects.filter(is_active=True).order_by("display_name")
        menu_serializer = MenuSerializer(menus, many=True)

        footer = FooterContent.get_active()
        footer_data = None
        if footer:
            footer_serializer = FooterContentSerializer(footer)
            footer_data = footer_serializer.data

        settings = SiteSettings.load()

        # Extract homepage_route from a "home" type menu item if present,
        # otherwise fall back to SiteSettings.
        homepage_route = settings.homepage_route
        for menu_data in menu_serializer.data:
            for item in menu_data.get("items", []):
                if item.get("type") == "home" and item.get("homepage_page"):
                    homepage_route = item["homepage_page"]
                    break

        data = {
            "menus": menu_serializer.data,
            "footer": footer_data,
            "homepage_mode": settings.homepage_mode,
            "homepage_route": homepage_route,
        }

        cache.set(cache_key, data, timeout=600)

        return Response(data)
