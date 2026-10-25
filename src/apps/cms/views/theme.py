from django.core.cache import cache
from django.http import HttpResponse, HttpResponseNotModified
from django.utils.cache import patch_cache_control
from django.utils.http import parse_etags
from django.views import View

from apps.cms.services.styles.theme import build_theme_css, theme_etag

from ..models import SiteSettings

THEME_CACHE_KEY = "layout:theme"
THEME_CACHE_TIMEOUT = 600
# Browsers and the CDN revalidate after five minutes; the CDN keeps serving the last copy while
# it revalidates, and for a week if the backend is down (the bundle carries fallback tokens).
THEME_CACHE_CONTROL = {"public": True, "max_age": 300, "stale_while_revalidate": 86400, "stale_if_error": 604800}


def etag_matches(if_none_match: str, etag: str) -> bool:
    """Weak comparison, as If-None-Match uses: ``W/"x"`` matches ``"x"``; ``*`` matches anything."""
    tags = parse_etags(if_none_match) if if_none_match else []
    return "*" in tags or any(tag.removeprefix("W/") == etag for tag in tags)


class ThemeStylesheetView(View):
    """The Site Settings design tokens and custom CSS as text/css, linked from index.html."""

    # noinspection PyMethodMayBeStatic
    def get(self, request, *args, **kwargs):
        cached = cache.get(THEME_CACHE_KEY)
        if cached is None:
            css = build_theme_css(SiteSettings.load())
            cached = (css, theme_etag(css))
            cache.set(THEME_CACHE_KEY, cached, timeout=THEME_CACHE_TIMEOUT)
        css, etag = cached

        if etag_matches(request.headers.get("If-None-Match", ""), etag):
            response = HttpResponseNotModified()
        else:
            response = HttpResponse(css, content_type="text/css; charset=utf-8")
        response["ETag"] = etag
        patch_cache_control(response, **THEME_CACHE_CONTROL)
        return response
