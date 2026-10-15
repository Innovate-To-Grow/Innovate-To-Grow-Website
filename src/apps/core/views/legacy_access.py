"""CloudFront-facing exchange endpoint for the legacy viewer."""

from django.http import Http404, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.core.services.legacy_access import (
    LegacyViewerAccessDenied,
    exchange_legacy_access_code,
    legacy_view_is_enabled,
    set_legacy_viewer_cookie,
)


def _no_store(response):
    response["Cache-Control"] = "private, no-store, max-age=0"
    response["Pragma"] = "no-cache"
    response["Referrer-Policy"] = "no-referrer"
    return response


@csrf_exempt
@require_POST
def legacy_access_exchange_view(request):
    """Redeem an opaque one-time code and start the viewer-only session."""

    if not legacy_view_is_enabled():
        raise Http404
    # The proxy gateway sets this marker only after its constant-time check of
    # the CloudFront custom origin header. Fail closed if this view is ever
    # accidentally mounted as a bare public URL.
    if getattr(request, "_i2g_legacy_origin_verified", False) is not True:
        raise Http404

    try:
        viewer_session = exchange_legacy_access_code(request.POST.get("code", ""))
    except LegacyViewerAccessDenied:
        return _no_store(HttpResponse("Access denied.", status=403, content_type="text/plain"))

    response = HttpResponse(status=303)
    response["Location"] = "/"
    set_legacy_viewer_cookie(response, viewer_session)
    return _no_store(response)
