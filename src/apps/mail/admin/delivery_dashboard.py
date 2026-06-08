"""Admin dashboard for AWS SES/IAM mail delivery health."""

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.template.response import TemplateResponse
from django.urls import path

from apps.core.access import user_can_access_app
from apps.mail.services.delivery_dashboard import get_delivery_dashboard_data

DEFAULT_DELIVERY_DASHBOARD_DAYS = 183
DELIVERY_DASHBOARD_WINDOWS = {
    7: {"label": "Last 7 days", "short_label": "7d"},
    90: {"label": "Last 3 months", "short_label": "3mo"},
    DEFAULT_DELIVERY_DASHBOARD_DAYS: {"label": "Last 6 months", "short_label": "6mo"},
    365: {"label": "Last 12 months", "short_label": "12mo"},
}


def get_delivery_dashboard_urls():
    return [
        path(
            "mail/delivery-dashboard/",
            admin.site.admin_view(delivery_dashboard_view),
            name="mail_delivery_dashboard",
        ),
        path(
            "mail/delivery-dashboard/data/",
            admin.site.admin_view(delivery_dashboard_data_view),
            name="mail_delivery_dashboard_data",
        ),
    ]


def delivery_dashboard_view(request):
    _require_mail_access(request)
    days = _dashboard_window_days(request)
    context = {
        **admin.site.each_context(request),
        "title": "Delivery Dashboard",
        "page_title": "Delivery Dashboard",
        "dashboard": get_delivery_dashboard_data(days=days),
        "dashboard_windows": _dashboard_window_options(days),
    }
    return TemplateResponse(request, "admin/mail/delivery_dashboard.html", context)


def delivery_dashboard_data_view(request):
    _require_mail_access(request)
    return JsonResponse(get_delivery_dashboard_data(days=_dashboard_window_days(request)))


def _require_mail_access(request):
    if not user_can_access_app(request.user, "mail"):
        raise PermissionDenied


def _dashboard_window_days(request) -> int:
    try:
        days = int(request.GET.get("days", DEFAULT_DELIVERY_DASHBOARD_DAYS))
    except (TypeError, ValueError):
        return DEFAULT_DELIVERY_DASHBOARD_DAYS
    return days if days in DELIVERY_DASHBOARD_WINDOWS else DEFAULT_DELIVERY_DASHBOARD_DAYS


def _dashboard_window_options(selected_days: int) -> list[dict]:
    return [
        {
            "days": days,
            "label": meta["label"],
            "short_label": meta["short_label"],
            "selected": days == selected_days,
        }
        for days, meta in DELIVERY_DASHBOARD_WINDOWS.items()
    ]
