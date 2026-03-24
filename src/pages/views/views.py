from django.core.cache import cache
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import FooterContent, Menu, SiteSettings
from ..serializers import (
    FooterContentSerializer,
    MenuSerializer,
)


class LayoutAPIView(APIView):
    """Unified endpoint for layout data (menus and footer) with caching."""

    permission_classes = [AllowAny]

    # noinspection PyMethodMayBeStatic
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

        data = {
            "menus": menu_serializer.data,
            "footer": footer_data,
            "homepage_route": settings.get_homepage_route(),
        }

        cache.set(cache_key, data, timeout=600)

        return Response(data)
