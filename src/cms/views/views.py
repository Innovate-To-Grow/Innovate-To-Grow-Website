from django.core.cache import cache
from django.http import HttpResponse
from django.utils.cache import patch_cache_control
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.clickjacking import xframe_options_exempt
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import CMSBlock, CMSEmbedWidget, FooterContent, Menu, SiteSettings, StyleSheet
from ..serializers import (
    CMSBlockSerializer,
    FooterContentSerializer,
    MenuSerializer,
)

LAYOUT_CACHE_KEY = "layout:data"
# Bump suffix (:v2, :v3, ...) whenever the assembled stylesheet gains or loses a
# non-token section. This retires existing cached blobs instantly on deploy
# instead of waiting the TTL out.
LAYOUT_STYLESHEET_CACHE_KEY = "layout:stylesheet:v3"
LAYOUT_CACHE_TIMEOUT = 600

# Mirrors GROUP_PREFIX in pages/src/components/Layout/LayoutProvider/LayoutProvider.tsx —
# both must agree so the CSS variables emitted server-side match the names JS sets.
_DESIGN_TOKEN_GROUP_PREFIX = {
    "colors": "color",
    "typography": "",
    "typography_mobile": "",
    "layout": "",
    "borders": "",
    "effects": "",
}


def _design_tokens_to_css(tokens):
    if not isinstance(tokens, dict):
        return ""
    lines = []
    for group, values in tokens.items():
        if not isinstance(values, dict):
            continue
        prefix = _DESIGN_TOKEN_GROUP_PREFIX.get(group, "")
        for key, value in values.items():
            kebab = key.replace("_", "-")
            var_name = f"--itg-{prefix}-{kebab}" if prefix else f"--itg-{kebab}"
            lines.append(f"  {var_name}: {value};")
    if not lines:
        return ""
    return ":root {\n" + "\n".join(lines) + "\n}\n"


class LayoutAPIView(APIView):
    """Unified endpoint for layout data (menus, footer, design tokens, stylesheets) with caching."""

    permission_classes = [AllowAny]

    # noinspection PyMethodMayBeStatic
    def get(self, request, *args, **kwargs):
        cached_data = cache.get(LAYOUT_CACHE_KEY)
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

        # Concatenate all active stylesheets in sort_order
        sheets = StyleSheet.objects.filter(is_active=True).values_list("css", flat=True)
        stylesheets_css = "\n".join(css for css in sheets if css)

        data = {
            "menus": menu_serializer.data,
            "footer": footer_data,
            "homepage_route": settings.get_homepage_route(),
            "design_tokens": settings.design_tokens,
            "stylesheets": stylesheets_css,
        }

        cache.set(LAYOUT_CACHE_KEY, data, timeout=LAYOUT_CACHE_TIMEOUT)

        return Response(data)


class LayoutStylesheetView(View):
    """Render-blocking stylesheet served as text/css.

    Linked from index.html so the browser fetches CSS in parallel with the
    main bundle and blocks rendering until styles arrive — eliminating the
    flash of unstyled content that occurred when CSS was injected by JS.
    """

    # noinspection PyMethodMayBeStatic
    def get(self, request, *args, **kwargs):
        css = cache.get(LAYOUT_STYLESHEET_CACHE_KEY)
        if css is None:
            settings = SiteSettings.load()
            tokens_css = _design_tokens_to_css(settings.design_tokens)
            sheets = StyleSheet.objects.filter(is_active=True).values_list("css", flat=True)
            sheets_css = "\n".join(c for c in sheets if c)
            css = (tokens_css + "\n" + sheets_css).strip() + "\n"
            cache.set(LAYOUT_STYLESHEET_CACHE_KEY, css, timeout=LAYOUT_CACHE_TIMEOUT)

        response = HttpResponse(css, content_type="text/css; charset=utf-8")
        patch_cache_control(response, public=True, max_age=LAYOUT_CACHE_TIMEOUT)
        return response


@method_decorator(xframe_options_exempt, name="dispatch")
class EmbedBlockView(APIView):
    """Public endpoint returning an embed widget's payload.

    Two widget types:
      - ``blocks`` — returns a subset of the source page's blocks plus page_css.
      - ``app_route`` — returns an interactive app-route identifier (e.g. "/schedule")
        the frontend mounts inside the embed iframe.

    Sets permissive CORS + removes X-Frame-Options so third parties can iframe-render.
    NOTE: the wildcard `Access-Control-Allow-Origin` is intentional — widgets are
    designed for arbitrary third-party embedding. To tighten this, add an
    `allowed_origins` field to CMSEmbedWidget and echo only matching origins.
    """

    permission_classes = [AllowAny]

    # noinspection PyMethodMayBeStatic
    def get(self, request, embed_slug, *args, **kwargs):
        widget = CMSEmbedWidget.objects.select_related("page").filter(slug=embed_slug).first()
        if widget is None or not self._is_visible(widget):
            response = Response({"detail": "Not found."}, status=404)
            response["Access-Control-Allow-Origin"] = "*"
            return response

        if widget.widget_type == "app_route":
            data = {
                "widget_type": "app_route",
                "app_route": widget.app_route,
                "blocks": [],
                "page_css_class": "",
                "page_css": "",
                "hide_section_titles": widget.hide_section_titles,
            }
        else:
            sort_orders = [o for o in (widget.block_sort_orders or []) if isinstance(o, int)]
            blocks_qs = CMSBlock.objects.filter(page_id=widget.page_id, sort_order__in=sort_orders)
            blocks_by_order = {b.sort_order: b for b in blocks_qs}
            ordered_blocks = [blocks_by_order[o] for o in sort_orders if o in blocks_by_order]
            data = {
                "widget_type": "blocks",
                "app_route": "",
                "blocks": CMSBlockSerializer(ordered_blocks, many=True).data,
                "page_css_class": widget.page.page_css_class or "",
                "page_css": widget.page.page_css or "",
                "hide_section_titles": widget.hide_section_titles,
            }
        response = Response(data)
        response["Access-Control-Allow-Origin"] = "*"
        return response

    # noinspection PyMethodMayBeStatic
    def _is_visible(self, widget):
        if widget.widget_type == "app_route":
            return bool(widget.app_route)
        return widget.page is not None and widget.page.status == "published"
