import logging
from datetime import timedelta

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.http import HttpResponseNotModified
from django.utils import timezone
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny, BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cms.models import CMSPage, RouteRedirect, SiteSettings
from apps.cms.serializers.cms import CMSPageSerializer
from apps.cms.services.routing.route_redirects import (
    normalize_and_validate_cms_page_route,
    normalize_and_validate_legacy_source,
)
from apps.cms.services.sanitization.embed_hosts import CACHE_TTL as EMBED_HOST_CACHE_TTL
from apps.cms.services.sanitization.embed_hosts import get_allowed_hosts_snapshot
from apps.core.utils.access import user_can_access_app
from apps.core.utils.http_cache import public_json_response

logger = logging.getLogger(__name__)

_LIVE_PREVIEW_TTL = 600  # 10 minutes
HOMEPAGE_CACHE_KEY = "cms:homepage"
CMS_PAGE_CACHE_TIMEOUT = 300


class CMSEmbedHostsView(APIView):
    """Publish the iframe allowlist used by browser-side sanitization."""

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


class HasCMSAppAccess(BasePermission):
    """Allow only members with admin access to the cms app.

    Mirrors the per-app gate used everywhere else (see
    apps.core.utils.access.user_can_access_app): superusers (I2G Master) and staff whose
    ``admin_apps`` includes "cms" are granted; everyone else is denied.
    """

    message = "CMS app access is required."

    def has_permission(self, request, view):
        return user_can_access_app(request.user, "cms")


class CMSPreviewFetchView(APIView):
    """Fetch cached preview data by token."""

    permission_classes = [AllowAny]

    # noinspection PyMethodMayBeStatic,PyUnusedLocal
    def get(self, request, token):
        data = cache.get(f"cms:preview:{token}")
        if data is None:
            return Response({"detail": "Preview not found or expired."}, status=404)
        return Response(data)


class CMSLivePreviewView(APIView):
    """Store and retrieve live-preview page data keyed by page UUID.

    POST (cms-app only): admin JS pushes the current editor state here on every edit.
    GET  (public cache): preview tab polls this endpoint to render the latest state.
                       cms-app members may fall back to the current DB state.
    """

    # Session auth needed for admin JS; JWT default handles API clients.
    authentication_classes = [SessionAuthentication]

    def get_permissions(self):
        if self.request.method == "POST":
            return [HasCMSAppAccess()]
        return [AllowAny()]

    # noinspection PyMethodMayBeStatic,PyUnusedLocal
    def get(self, request, page_id):
        cached = cache.get(f"cms:live-preview:{page_id}")
        if cached is not None:
            return Response(cached)

        if not user_can_access_app(request.user, "cms"):
            return Response({"detail": "Preview not found or expired."}, status=404)

        page = CMSPage.objects.prefetch_related("blocks").filter(pk=page_id).first()
        if page is None:
            return Response({"detail": "Page not found."}, status=404)
        return Response(CMSPageSerializer(page).data)

    # noinspection PyMethodMayBeStatic
    def post(self, request, page_id):
        import json

        data = request.data
        if not isinstance(data, dict):
            return Response({"detail": "Invalid JSON."}, status=400)

        # Reject oversize payloads before they hit the cache / GET reflection.
        # 512 KB is ~10x a typical page payload and small enough that the GET
        # reflection cannot be used to blow up downstream consumers.
        try:
            serialized_size = len(json.dumps(data, default=str))
        except (TypeError, ValueError):
            return Response({"detail": "Payload is not serializable."}, status=400)
        if serialized_size > 512_000:
            return Response({"detail": "Preview payload too large."}, status=413)

        data.pop("expires_at", None)
        data["expires_at"] = (timezone.now() + timedelta(seconds=_LIVE_PREVIEW_TTL)).isoformat()
        cache.set(f"cms:live-preview:{page_id}", data, timeout=_LIVE_PREVIEW_TTL)
        return Response({"ok": True})


class CMSPageView(APIView):
    """Serve a published CMS page by its route path."""

    permission_classes = [AllowAny]

    # noinspection PyMethodMayBeStatic
    def get(self, request, route_path=""):
        raw_route = f"/{route_path}" if route_path else "/"
        if raw_route.startswith("//"):
            return Response({"detail": "Page not found."}, status=404)
        is_preview = request.query_params.get("preview") == "true"

        if not is_preview:
            try:
                legacy_route = normalize_and_validate_legacy_source(raw_route)
            except ValidationError:
                legacy_route = None

            if legacy_route is not None:
                cached = cache.get(f"cms:page:{legacy_route}")
                if cached is not None:
                    return public_json_response(request, cached)

                redirect = (
                    RouteRedirect.objects.filter(source_path=legacy_route, is_active=True)
                    .only("destination_path")
                    .first()
                )
                if redirect is not None:
                    data = {"redirect_to": redirect.destination_path, "permanent": True}
                    cache.set(f"cms:page:{legacy_route}", data, timeout=CMS_PAGE_CACHE_TIMEOUT)
                    return public_json_response(request, data)

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

    permission_classes = [AllowAny]

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
