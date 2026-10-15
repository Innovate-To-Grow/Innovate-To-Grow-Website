import logging

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from apps.authn.security import SoftJWTAuthentication
from apps.cms.serializers import PageViewCreateSerializer
from apps.cms.services.analytics import clean_visitor_id, enqueue
from apps.core.utils.throttle_cache import throttle_cache

logger = logging.getLogger(__name__)

# All three throttles below are fairness limiters over analytics rows: nothing user-facing, no money and no
# security decision depends on them, and none of them reads the client IP (campus visitors share one). Their
# history is in the bounded in-process ``throttle`` cache, never in the default cache: the per-visitor key is
# chosen by the client, and in the production file cache every minted key would be one more file that slows down
# each cache write of the container. In-process means per Uvicorn worker, so with WEB_CONCURRENCY=2 a container
# admits up to twice each rate, and a restart forgets the history.


def _visitor_id(request) -> str | None:
    """The well-formed ``visitor_id`` of the request body, or ``None`` (absent, malformed, or not a JSON object)."""
    data = request.data
    return clean_visitor_id(data.get("visitor_id")) if hasattr(data, "get") else None


class PageViewVisitorThrottle(SimpleRateThrottle):
    """Per-visitor page-view rate, keyed on the browser's ``visitor_id``. The client IP is never part of the key.

    Campus visitors share one public IP: a per-IP rate dropped most campus page views on a busy day. One browser
    cannot produce 120 real page views a minute, so this only stops a runaway client. The id is client-chosen, so a
    deliberate flood can mint fresh ones; that is no weaker than the old per-IP key (forgeable through
    ``X-Forwarded-For``) and spends no money. What bounds such a flood is ``PageViewTotalThrottle`` here and a
    rate rule at the edge (docs/deployment/waf-rate-limits.md), never the client IP.
    """

    scope = "pageview_visitor"
    rate = "120/min"
    cache = throttle_cache

    def get_cache_key(self, request, view):
        visitor_id = _visitor_id(request)
        if visitor_id is None:
            return None
        return self.cache_format % {"scope": self.scope, "ident": f"visitor:{visitor_id}"}


class PageViewLegacyThrottle(SimpleRateThrottle):
    """One shared bucket for page views that carry no usable ``visitor_id``.

    Those come from frontend bundles cached before the id existed (the frontend and the backend deploy
    independently) and from anything else that omits it or sends a malformed one. 600 a minute per process is
    several times the estimated busiest campus minute (about 150 page views), so honest traffic should never reach
    it; it only caps how fast id-less junk can be written.
    """

    scope = "pageview_legacy"
    rate = "600/min"
    cache = throttle_cache

    def get_cache_key(self, request, view):
        if _visitor_id(request) is not None:
            return None
        return self.cache_format % {"scope": self.scope, "ident": "legacy"}


class PageViewTotalThrottle(SimpleRateThrottle):
    """One bucket for ALL page views of this process, whoever sends them: the bound on what a flood can write.

    A script that mints a fresh ``visitor_id`` per request never meets the per-visitor rate, and every accepted
    page view is a row in a table without retention. 3,000 a minute per process is about twenty times the estimated
    busiest campus minute (150 page views), so honest traffic does not come near it. Above it the answer is the
    ordinary 429, which the frontend ignores: analytics rows are dropped during a flood and nothing a visitor can
    see is blocked. The key is a constant, so one sender can use up the allowance for everyone; that only costs
    statistics for that minute.

    Checked in two steps so that only accepted page views count. ``allow_request`` refuses while the bucket is
    full and otherwise leaves it untouched; the view calls ``record`` once the per-visitor / legacy throttle has
    accepted the request. A single runaway browser therefore uses 120 of the 3,000, not all of them, and while
    the bucket is full a minted id is refused before it gets a history entry of its own.
    """

    scope = "pageview_total"
    rate = "3000/min"
    cache = throttle_cache

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": "all"}

    def throttle_success(self):
        """There is room, but do not count the request yet: ``record`` does, once the other throttles agree."""
        return True

    def record(self):
        """Count the request that ``allow_request`` has just admitted."""
        return super().throttle_success()

    def warn_reached(self):
        """Operator signal that page views are being dropped: at most one line a minute per process."""
        if self.cache.add("pageview_total_cap_warned", 1, timeout=60):
            logger.warning(
                "analytics.pageview_total_cap limit=%d window_seconds=%d: page views over the cap are "
                "answered 429 and not recorded in this process",
                self.num_requests,
                self.duration,
            )


class PageViewCreateView(APIView):
    """Accept page-view tracking events from the frontend."""

    # Attributes the view to the member behind a valid token; a stale token records it as anonymous, not a 401.
    authentication_classes = [SoftJWTAuthentication]
    permission_classes = [AllowAny]
    throttle_classes = [PageViewVisitorThrottle, PageViewLegacyThrottle]

    def check_throttles(self, request):
        """The per-visitor / legacy throttles, inside the total cap (see ``PageViewTotalThrottle``)."""
        total = PageViewTotalThrottle()
        if not total.allow_request(request, self):
            total.warn_reached()
            self.throttled(request, total.wait())
        super().check_throttles(request)
        total.record()

    @staticmethod
    def _get_client_ip(request):
        """Return the originating client IP, honouring NUM_PROXIES trusted hops.

        X-Forwarded-For is a comma-separated list appended-to by each proxy.
        With ``NUM_PROXIES = N``, the rightmost N entries are trusted proxy
        hops; the Nth-from-right entry is the actual client. If NUM_PROXIES
        is not configured (dev / tests), fall back to the leftmost entry.
        """
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded:
            parts = [p.strip() for p in forwarded.split(",") if p.strip()]
            if parts:
                num_proxies = getattr(settings, "NUM_PROXIES", None)
                if num_proxies:
                    index = max(0, len(parts) - num_proxies)
                    return parts[index]
                return parts[0]
        return request.META.get("REMOTE_ADDR")

    def post(self, request, *args, **kwargs):
        serializer = PageViewCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        member = request.user if request.user.is_authenticated else None
        enqueue(
            {
                "path": serializer.validated_data["path"],
                "referrer": serializer.validated_data.get("referrer", ""),
                "ip_address": self._get_client_ip(request),
                "visitor_id": _visitor_id(request),
                "user_agent": request.META.get("HTTP_USER_AGENT", ""),
                "member": member,
                "session_key": getattr(request.session, "session_key", None) or "",
            }
        )
        return Response(status=status.HTTP_201_CREATED)
