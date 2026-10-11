"""CSRF-protected launch flow for the read-only legacy viewer."""

import re
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.template.response import TemplateResponse
from django.views.decorators.http import require_http_methods

from apps.core.services.legacy_access import issue_legacy_access_grant, legacy_view_is_enabled
from apps.core.utils.access import user_can_access_app

_CLOUDFRONT_HOST_PATTERN = re.compile(r"^d[a-z0-9]+\.cloudfront\.net$")


def _legacy_viewer_base_url() -> str | None:
    value = str(getattr(settings, "LEGACY_VIEWER_URL", "") or "").strip()
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return None
    hostname = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or not _CLOUDFRONT_HOST_PATTERN.fullmatch(hostname)
        or port not in {None, 443}
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        return None
    return f"https://{hostname}"


def _require_core_access(request) -> None:
    if not user_can_access_app(request.user, "core"):
        raise PermissionDenied("You do not have permission to open the legacy viewer.")


def _no_store(response):
    response["Cache-Control"] = "private, no-store, max-age=0"
    response["Referrer-Policy"] = "no-referrer"
    return response


@require_http_methods(["GET", "POST"])
def legacy_view_launch(request, *, admin_site=None):
    """Render the launch button, then hand a one-time code to CloudFront."""

    if not legacy_view_is_enabled():
        raise Http404
    _require_core_access(request)

    viewer_url = _legacy_viewer_base_url()
    exchange_url = f"{viewer_url}/_i2g-auth/exchange" if viewer_url else ""
    context = {
        **(admin_site or admin.site).each_context(request),
        "title": "Legacy read-only viewer",
        "page_title": "Legacy read-only viewer",
        "exchange_url": exchange_url,
        "viewer_url": viewer_url,
        "launch_code": "",
    }
    status = 200
    if request.method == "POST":
        if not exchange_url:
            status = 503
        else:
            issued = issue_legacy_access_grant(request)
            context["launch_code"] = issued.code

    response = TemplateResponse(
        request,
        "admin/legacy_view/launch.html",
        context,
        status=status,
    )
    if viewer_url:
        # The CSP middleware validates and adds only this origin to form-action
        # for this response; every other Admin page remains same-origin-only.
        response.csp_form_action_origins = (viewer_url,)
    return _no_store(response)
