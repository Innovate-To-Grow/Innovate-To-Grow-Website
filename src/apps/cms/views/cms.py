import logging

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.http import HttpResponseNotModified
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authn.security import SoftJWTAuthentication
from apps.cms.models import CMSPage, RouteRedirect, SiteSettings
from apps.cms.serializers.cms import CMSPageSerializer
from apps.cms.services.routing.route_redirects import (
    normalize_and_validate_cms_page_route,
    normalize_and_validate_legacy_source,
)
from apps.cms.services.sanitization.embed_hosts import CACHE_TTL as EMBED_HOST_CACHE_TTL
from apps.cms.services.sanitization.embed_hosts import get_allowed_hosts_snapshot
from apps.cms.views.cms_preview import CMSLivePreviewView as CMSLivePreviewView
from apps.cms.views.cms_preview import CMSPreviewFetchView as CMSPreviewFetchView
from apps.core.utils.access import user_can_access_app
from apps.core.utils.http_cache import public_json_response

logger = logging.getLogger(__name__)

HOMEPAGE_CACHE_KEY = "cms:homepage"
CMS_PAGE_CACHE_TIMEOUT = 300


class CMSEmbedHostsView(APIView):
    """Publish the iframe allowlist used by browser-side sanitization."""

    rate_limit_scope = "public-background"

    permission_classes = [AllowAny]
    authentication_classes = []

    # noinspection PyMethodMayBeStatic
    def get(self, request):
        snapshot = get_allowed_hosts_snapshot()
        etag = f'"{snapshot["revision"]}"'
        if request.headers.get("If-None-Match") == etag:
            response = HttpResponseNotModified()
        else:
            response = Response(snapshot)
        response["ETag"] = etag
        response["Cache-Control"] = (
            f"public, max-age={EMBED_HOST_CACHE_TTL}, stale-while-revalidate={EMBED_HOST_CACHE_TTL}"
        )
        return response


def _legacy_route_response(request, raw_route: str):
    """The cached page or redirect for a legacy (pre-CMS) URL, or None to resolve it as a CMS route."""
    try:
        legacy_route = normalize_and_validate_legacy_source(raw_route)
    except ValidationError:
        return None
    if legacy_route is None:
        return None
    cached = cache.get(f"cms:page:{legacy_route}")
    if cached is not None:
        return public_json_response(request, cached)
    redirect = RouteRedirect.objects.filter(source_path=legacy_route, is_active=True).only("destination_path").first()
    if redirect is None:
        return None
    data = {"redirect_to": redirect.destination_path, "permanent": True}
    cache.set(f"cms:page:{legacy_route}", data, timeout=CMS_PAGE_CACHE_TIMEOUT)
    return public_json_response(request, data)


class CMSPageView(APIView):
    """Serve a published CMS page by its route path."""

    rate_limit_scope = "public-read"

    permission_classes = [AllowAny]
    # ``?preview=true`` shows a draft to an Admin, so a valid token is honoured; a stale one is anonymous.
    authentication_classes = [SoftJWTAuthentication]

    # noinspection PyMethodMayBeStatic
    def get(self, request, route_path=""):
        raw_route = f"/{route_path}" if route_path else "/"
        if raw_route.startswith("//"):
            return Response({"detail": "Page not found."}, status=404)
        is_preview = request.query_params.get("preview") == "true"

        if not is_preview:
            legacy_response = _legacy_route_response(request, raw_route)
            if legacy_response is not None:
                return legacy_response

        try:
            route = normalize_and_validate_cms_page_route(raw_route)
        except ValidationError:
            return Response({"detail": "Page not found."}, status=404)

        qs = CMSPage.objects.prefetch_related("blocks")
        if is_preview and user_can_access_app(request.user, "cms"):
            qs = qs.filter(route=route).exclude(status="archived")
        else:
            qs = qs.filter(route=route, status="published")

        page = qs.first()
        if page is None:
            return Response({"detail": "Page not found."}, status=404)

        data = CMSPageSerializer(page).data

        if not is_preview:
            cache.set(f"cms:page:{route}", data, timeout=CMS_PAGE_CACHE_TIMEOUT)
            return public_json_response(request, data)

        return Response(data)


class CMSHomepageView(APIView):
    """Serve the selected published homepage, falling back to the published root page."""

    rate_limit_scope = "public-read"

    permission_classes = [AllowAny]
    authentication_classes = []

    # noinspection PyMethodMayBeStatic
    def get(self, request):
        cached = cache.get(HOMEPAGE_CACHE_KEY)
        if cached is not None:
            return public_json_response(request, cached)

        settings = SiteSettings.load()
        pages = CMSPage.objects.prefetch_related("blocks").filter(status="published")
        page = None
        if settings.homepage_page_id:
            page = pages.filter(pk=settings.homepage_page_id).first()
        if page is None:
            page = pages.filter(route="/").first()
        if page is None:
            return Response({"detail": "Page not found."}, status=404)

        data = CMSPageSerializer(page).data
        cache.set(HOMEPAGE_CACHE_KEY, data, timeout=CMS_PAGE_CACHE_TIMEOUT)
        return public_json_response(request, data)
