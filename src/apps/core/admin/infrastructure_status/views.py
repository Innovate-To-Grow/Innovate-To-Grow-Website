"""Staff-only infrastructure dashboard views."""

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.template.response import TemplateResponse
from django.views.decorators.http import require_GET

from apps.core.services.status import get_infrastructure_dashboard, get_public_status_url
from apps.core.utils.access import user_can_access_app


def _require_core_access(request) -> None:
    # AdminSite.admin_view only checks active staff status. Standalone custom
    # pages do not pass through BaseModelAdmin's per-app permission hooks.
    if not user_can_access_app(request.user, "core"):
        raise PermissionDenied("You do not have permission to view infrastructure status.")


def _no_store(response):
    response["Cache-Control"] = "private, no-store, max-age=0"
    return response


@require_GET
def infrastructure_status_view(request, *, admin_site=None):
    """Render the Unfold infrastructure detail dashboard."""

    _require_core_access(request)
    dashboard = get_infrastructure_dashboard()
    site = admin_site or admin.site
    context = {
        **site.each_context(request),
        "title": "Infrastructure Status",
        "page_title": "Infrastructure Status",
        "dashboard": dashboard,
        "public_status_url": get_public_status_url(),
    }
    return _no_store(TemplateResponse(request, "admin/status/infrastructure.html", context))


@require_GET
def infrastructure_status_data_view(request, *, admin_site=None):  # noqa: ARG001
    """Return refreshed infrastructure data for the dashboard UI."""

    _require_core_access(request)
    force = request.GET.get("force") == "1"
    return _no_store(JsonResponse(get_infrastructure_dashboard(force=force)))
