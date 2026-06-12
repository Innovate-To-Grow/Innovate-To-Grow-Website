from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.template.response import TemplateResponse

from apps.core.access import user_can_access_app
from apps.system_intelligence.services.usage_stats import get_dashboard_context


def usage_dashboard_view(request):
    """Render the assistant usage big-screen dashboard."""
    # admin_view only enforces is_staff; re-check the per-app model here.
    if not user_can_access_app(request.user, "system_intelligence"):
        raise PermissionDenied("You do not have permission to access System Intelligence.")
    context = {
        **admin.site.each_context(request),
        "title": "Usage Dashboard",
        "page_title": "Assistant Usage",
        **get_dashboard_context(),
    }
    return TemplateResponse(request, "admin/system_intelligence/usage_dashboard.html", context)


def usage_dashboard_data_view(request):
    """Return the dashboard context as JSON (used by the TV-mode auto-refresh)."""
    # admin_view only enforces is_staff; re-check the per-app model here.
    if not user_can_access_app(request.user, "system_intelligence"):
        raise PermissionDenied("You do not have permission to access System Intelligence.")
    force = request.GET.get("force") == "1"
    return JsonResponse(get_dashboard_context(force=force))
