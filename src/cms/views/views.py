from django.core.cache import cache
from django.http import HttpResponse
from django.utils.cache import patch_cache_control
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.clickjacking import xframe_options_exempt
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import CMSBlock, CMSPage, FooterContent, Menu, SiteSettings, StyleSheet
from ..serializers import (
    CMSBlockSerializer,
    FooterContentSerializer,
    MenuSerializer,
)

LAYOUT_CACHE_KEY = "layout:data"
LAYOUT_STYLESHEET_CACHE_KEY = "layout:stylesheet"
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
    """Public endpoint returning all blocks for a named embed widget.

    Embed widgets are configured on ``CMSPage.embed_configs`` as a list of
    ``{slug, block_sort_orders, admin_label}`` entries. Slugs are unique across
    all pages. Only published pages resolve.

    Sets permissive CORS + removes X-Frame-Options so third parties can iframe-render.
    """

    permission_classes = [AllowAny]

    # noinspection PyMethodMayBeStatic
    def get(self, request, embed_slug, *args, **kwargs):
        # JSONField containment: find the page whose embed_configs contains an
        # entry with matching slug. Works on SQLite 3.38+ and PostgreSQL.
        page = (
            CMSPage.objects.filter(
                status="published",
                embed_configs__contains=[{"slug": embed_slug}],
            )
            .only("page_css_class", "page_css", "embed_configs")
            .first()
        )
        entry = None
        if page is not None:
            entry = next(
                (e for e in (page.embed_configs or []) if isinstance(e, dict) and e.get("slug") == embed_slug),
                None,
            )
        if page is None or entry is None:
            response = Response({"detail": "Not found."}, status=404)
            response["Access-Control-Allow-Origin"] = "*"
            return response

        sort_orders = [o for o in (entry.get("block_sort_orders") or []) if isinstance(o, int)]
        blocks_qs = CMSBlock.objects.filter(page_id=page.pk, sort_order__in=sort_orders)
        blocks_by_order = {b.sort_order: b for b in blocks_qs}
        ordered_blocks = [blocks_by_order[o] for o in sort_orders if o in blocks_by_order]

        data = {
            "blocks": CMSBlockSerializer(ordered_blocks, many=True).data,
            "page_css_class": page.page_css_class or "",
            "page_css": page.page_css or "",
        }
        response = Response(data)
        response["Access-Control-Allow-Origin"] = "*"
        return response
