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
# non-token section (e.g. the init-loader CSS below). This retires existing
# cached blobs instantly on deploy instead of waiting the TTL out.
LAYOUT_STYLESHEET_CACHE_KEY = "layout:stylesheet:v2"
LAYOUT_CACHE_TIMEOUT = 600

# Initial-load spinner. Shown via the #root:empty pseudo-class, so it appears
# the moment /layout/styles.css arrives (body.itg-styles-ready flips on in
# index.html) and disappears automatically the instant React mounts content
# into #root. Pure CSS, no JS hook required.
_INIT_LOADER_CSS = """
/* ---- init loader ---- */
@keyframes itg-init-loader-spin { to { transform: rotate(360deg); } }
@keyframes itg-init-loader-fade-in { from { opacity: 0; } to { opacity: 1; } }
#root:empty::before {
  content: "";
  display: block;
  width: 44px;
  height: 44px;
  margin: 96px auto;
  border: 3px solid rgba(15, 45, 82, 0.15);
  border-top-color: var(--itg-color-primary, #0f2d52);
  border-radius: 50%;
  animation:
    itg-init-loader-spin 0.9s linear infinite,
    itg-init-loader-fade-in 0.25s ease-out;
}
/* Strip the loader in iframe-isolated routes (block preview + embed widget). */
html[data-block-preview] #root:empty::before { display: none; }
@media (prefers-reduced-motion: reduce) {
  #root:empty::before {
    animation: itg-init-loader-fade-in 0.25s ease-out;
    opacity: 0.7;
  }
}
"""

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
            css = (tokens_css + "\n" + sheets_css).strip() + "\n" + _INIT_LOADER_CSS
            cache.set(LAYOUT_STYLESHEET_CACHE_KEY, css, timeout=LAYOUT_CACHE_TIMEOUT)

        response = HttpResponse(css, content_type="text/css; charset=utf-8")
        patch_cache_control(response, public=True, max_age=LAYOUT_CACHE_TIMEOUT)
        return response


@method_decorator(xframe_options_exempt, name="dispatch")
class EmbedBlockView(APIView):
    """Public endpoint returning all blocks for a named embed widget.

    Sets permissive CORS + removes X-Frame-Options so third parties can iframe-render.
    """

    permission_classes = [AllowAny]

    # noinspection PyMethodMayBeStatic
    def get(self, request, embed_slug, *args, **kwargs):
        widget = CMSEmbedWidget.objects.select_related("page").filter(page__status="published", slug=embed_slug).first()
        if widget is None:
            response = Response({"detail": "Not found."}, status=404)
            response["Access-Control-Allow-Origin"] = "*"
            return response

        sort_orders = [o for o in (widget.block_sort_orders or []) if isinstance(o, int)]
        blocks_qs = CMSBlock.objects.filter(page_id=widget.page_id, sort_order__in=sort_orders)
        blocks_by_order = {b.sort_order: b for b in blocks_qs}
        ordered_blocks = [blocks_by_order[o] for o in sort_orders if o in blocks_by_order]

        data = {
            "blocks": CMSBlockSerializer(ordered_blocks, many=True).data,
            "page_css_class": widget.page.page_css_class or "",
            "page_css": widget.page.page_css or "",
        }
        response = Response(data)
        response["Access-Control-Allow-Origin"] = "*"
        return response
