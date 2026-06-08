"""Admin dashboard for AWS SES/IAM mail delivery health."""

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.template.response import TemplateResponse
from django.urls import path

from apps.core.access import user_can_access_app
from apps.mail.services.delivery_dashboard import get_delivery_dashboard_data


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
    context = {
        **admin.site.each_context(request),
        "title": "Delivery Dashboard",
        "page_title": "Delivery Dashboard",
        "dashboard": get_delivery_dashboard_data(),
    }
    return TemplateResponse(request, "admin/mail/delivery_dashboard.html", context)


def delivery_dashboard_data_view(request):
    _require_mail_access(request)
    return JsonResponse(get_delivery_dashboard_data())


def _require_mail_access(request):
    if not user_can_access_app(request.user, "mail"):
        raise PermissionDenied
