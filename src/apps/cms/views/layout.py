from django.core.cache import cache
from django.utils.decorators import method_decorator
from django.views.decorators.clickjacking import xframe_options_exempt
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cms.app_routes import widget_supports_schedule
from apps.core.utils.http_cache import public_json_response

from ..models import CMSBlock, CMSEmbedWidget, FooterContent, Menu
from ..serializers import (
    CMSBlockSerializer,
    FooterContentSerializer,
    MenuSerializer,
)

LAYOUT_CACHE_KEY = "layout:data"
LAYOUT_CACHE_TIMEOUT = 600


class LayoutAPIView(APIView):
    """Unified endpoint for menu and footer data with caching."""

    permission_classes = [AllowAny]
    authentication_classes = []

    # noinspection PyMethodMayBeStatic
    def get(self, request, *args, **kwargs):
        cached_data = cache.get(LAYOUT_CACHE_KEY)
        if cached_data is not None:
            return public_json_response(request, cached_data)

        menus = Menu.objects.filter(is_active=True).order_by("display_name")
        menu_serializer = MenuSerializer(menus, many=True)

        footer = FooterContent.get_active()
        footer_data = None
        if footer:
            footer_serializer = FooterContentSerializer(footer)
            footer_data = footer_serializer.data

        data = {
            "menus": menu_serializer.data,
            "footer": footer_data,
        }

        cache.set(LAYOUT_CACHE_KEY, data, timeout=LAYOUT_CACHE_TIMEOUT)

        return public_json_response(request, data)


@method_decorator(xframe_options_exempt, name="dispatch")
class EmbedBlockView(APIView):
    """Public endpoint returning an embed widget's payload.

    Two widget types:
      - ``blocks`` — returns a subset of the source page's blocks and its page class.
      - ``app_route`` — returns an interactive app-route identifier (e.g. "/schedule")
        the frontend mounts inside the embed iframe.

    Sets permissive CORS + removes X-Frame-Options so third parties can iframe-render.
    NOTE: the wildcard `Access-Control-Allow-Origin` is intentional — widgets are
    designed for arbitrary third-party embedding. To tighten this, add an
    `allowed_origins` field to CMSEmbedWidget and echo only matching origins.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    # noinspection PyMethodMayBeStatic
    def get(self, request, embed_slug, *args, **kwargs):
        widget = CMSEmbedWidget.objects.select_related("page", "schedule").filter(slug=embed_slug).first()
        if widget is None or not widget.is_visible():
            response = Response({"detail": "Not found."}, status=404)
            response["Access-Control-Allow-Origin"] = "*"
            return response

        if widget.widget_type == "app_route":
            hidden_sections = widget.get_effective_hidden_sections()
            data = {
                "widget_type": "app_route",
                "app_route": widget.app_route,
                "blocks": [],
                "page_css_class": "",
                "hidden_sections": hidden_sections,
                "hide_section_titles": "section_titles" in hidden_sections,
                "schedule_id": str(widget.schedule_id)
                if widget_supports_schedule(widget) and widget.schedule_id
                else None,
            }
        else:
            hidden_sections = widget.get_effective_hidden_sections()
            sort_orders = [o for o in (widget.block_sort_orders or []) if isinstance(o, int)]
            blocks_qs = CMSBlock.objects.filter(page_id=widget.page_id, sort_order__in=sort_orders)
            blocks_by_order = {b.sort_order: b for b in blocks_qs}
            ordered_blocks = [blocks_by_order[o] for o in sort_orders if o in blocks_by_order]
            data = {
                "widget_type": "blocks",
                "app_route": "",
                "blocks": CMSBlockSerializer(ordered_blocks, many=True).data,
                "page_css_class": widget.page.page_css_class or "",
                "hidden_sections": hidden_sections,
                "hide_section_titles": "section_titles" in hidden_sections,
            }
        response = Response(data)
        response["Access-Control-Allow-Origin"] = "*"
        return response
