"""Custom Django REST Framework renderers used by the public API."""

from rest_framework.permissions import SAFE_METHODS
from rest_framework.renderers import BrowsableAPIRenderer

BROWSABLE_API_CACHE_CONTROL = "private, no-store, max-age=0"
BROWSABLE_API_ROBOTS = "noindex, nofollow, noarchive"


class UCMercedBrowsableAPIRenderer(BrowsableAPIRenderer):
    """Render DRF's interactive interface with UC Merced branding.

    Browsable API responses can contain user-specific forms and CSRF tokens, so
    they must never inherit the public caching policy used by JSON endpoints.
    """

    template = "rest_framework/uc_merced_api.html"

    def get_context(self, data, accepted_media_type, renderer_context):
        context = super().get_context(data, accepted_media_type, renderer_context)
        # The upstream template emits Pygments rules in an inline <style>
        # element. The branded theme supplies those rules from static CSS so
        # the page remains compatible with a nonce-based production CSP.
        context["code_style"] = None
        return context

    def render(self, data, accepted_media_type=None, renderer_context=None):
        renderer_context = renderer_context or {}
        response = renderer_context.get("response")
        if response is not None:
            response["Cache-Control"] = BROWSABLE_API_CACHE_CONTROL
            response["X-Robots-Tag"] = BROWSABLE_API_ROBOTS
            response.headers.pop("ETag", None)

        rendered = super().render(data, accepted_media_type, renderer_context)

        request = renderer_context.get("request")
        view = renderer_context.get("view")
        if request is not None and view is not None and self._is_anonymous_read_only(request, view):
            # DRF's base template always renders a CSRF value for its JavaScript.
            # A read-only anonymous page has no form that can use it, so prevent
            # CsrfViewMiddleware from emitting a needless, cache-hostile cookie.
            request.META.pop("CSRF_COOKIE_NEEDS_UPDATE", None)

        return rendered

    @staticmethod
    def _is_anonymous_read_only(request, view):
        user = getattr(request, "user", None)
        is_authenticated = bool(getattr(user, "is_authenticated", False))
        return not is_authenticated and set(view.allowed_methods).issubset(SAFE_METHODS)
