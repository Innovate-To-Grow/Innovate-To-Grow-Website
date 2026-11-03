"""The public sitemap of the frontend domain: published CMS pages, content app routes and other apps' pages."""

import logging
from datetime import UTC
from html import escape
from urllib.parse import quote

from django.conf import settings
from django.db.models import Max
from django.http import HttpResponse
from django.utils import timezone
from django.utils.module_loading import import_string

from apps.cms.app_routes import SITEMAP_APP_ROUTES
from apps.cms.models import CMSPage

logger = logging.getLogger(__name__)

SITEMAP_XMLNS = "http://www.sitemaps.org/schemas/sitemap/0.9"


def _canonical_frontend_base(request):
    base = (getattr(settings, "FRONTEND_URL", "") or "").strip().rstrip("/")
    if base:
        return base
    return request.build_absolute_uri("/").rstrip("/")


def _sitemap_url(base, route):
    if route == "/":
        return f"{base}/"
    quoted_path = quote(route, safe="/")
    return f"{base}{quoted_path}"


def _format_lastmod(value):
    if value is None:
        return ""
    return timezone.localtime(value, timezone=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sitemap_lastmod(page):
    candidates = [page.updated_at, page.published_at, getattr(page, "latest_block_updated_at", None)]
    return _format_lastmod(max((value for value in candidates if value), default=None))


def _provided_entries():
    """(route, lastmod) pairs other apps contribute through settings.SITEMAP_ENTRY_PROVIDERS."""
    entries = []
    for provider in getattr(settings, "SITEMAP_ENTRY_PROVIDERS", ()):
        try:
            entries.extend((route, _format_lastmod(lastmod)) for route, lastmod in import_string(provider)())
        except Exception:
            # One app's pages failing to load must not take the rest of the sitemap down.
            logger.exception("Sitemap entry provider %s failed; its pages are left out", provider)
    return entries


def _sitemap_entries():
    pages = (
        CMSPage.objects.filter(status="published")
        .annotate(latest_block_updated_at=Max("blocks__updated_at"))
        .order_by("route")
    )
    entries = [(page.route, _sitemap_lastmod(page)) for page in pages]
    cms_routes = {route for route, _lastmod in entries}
    entries.extend((route, "") for route in SITEMAP_APP_ROUTES if route not in cms_routes)
    entries.extend(_provided_entries())
    return entries


def sitemap_xml(request):
    """Serve the public sitemap for the frontend domain."""
    base = _canonical_frontend_base(request)
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', f'<urlset xmlns="{SITEMAP_XMLNS}">']
    for route, lastmod in _sitemap_entries():
        lines.append("  <url>")
        lines.append(f"    <loc>{escape(_sitemap_url(base, route))}</loc>")
        if lastmod:
            lines.append(f"    <lastmod>{lastmod}</lastmod>")
        lines.append("  </url>")
    lines.append("</urlset>")
    return HttpResponse("\n".join(lines), content_type="application/xml")


sitemap_xml.rate_limit_scope = "public-background"
