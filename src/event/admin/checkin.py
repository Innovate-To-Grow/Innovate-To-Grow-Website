from django.contrib import admin
from django.db.models import Count
from django.http import Http404
from django.middleware.csrf import get_token
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from unfold.decorators import display

from core.admin import BaseModelAdmin, ReadOnlyModelAdmin

from ..models import CheckIn, CheckInRecord


@admin.register(CheckIn)
class CheckInAdmin(BaseModelAdmin):
    change_form_template = "admin/event/checkin/change_form.html"
    list_display = ("name", "event", "is_active_badge", "scan_count_display", "scanner_link", "created_at")
    list_filter = ("event", "is_active")
    search_fields = ("name", "event__name")
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (
            None,
            {"fields": ("event", "name", "is_active")},
        ),
        (
            "System",
            {
                "classes": ("collapse",),
                "fields": ("created_at", "updated_at"),
            },
        ),
    )

    @display(description="Active", label=True)
    def is_active_badge(self, obj):
        if obj.is_active:
            return "Active", "success"
        return "Closed", "info"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(_scan_count=Count("records"))

    @admin.display(description="Scans", ordering="_scan_count")
    def scan_count_display(self, obj):
        return getattr(obj, "_scan_count", obj.scan_count)

    @admin.display(description="Scanner")
    def scanner_link(self, obj):
        if not obj.pk:
            return "-"
        url = reverse("admin:event_checkin_scanner", args=[obj.pk])
        return format_html('<a href="{}" target="_blank">Open Console</a>', url)

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<path:object_id>/scanner/",
                self.admin_site.admin_view(self.scanner_view),
                name="event_checkin_scanner",
            ),
        ]
        return custom + urls

    def scanner_view(self, request, object_id):
        try:
            check_in = CheckIn.objects.select_related("event").get(pk=object_id)
        except CheckIn.DoesNotExist:
            raise Http404

        context = {
            **self.admin_site.each_context(request),
            "title": f"Check-in Console — {check_in.name}",
            "check_in": check_in,
            "scan_url": f"/event/check-in/{check_in.pk}/scan/",
            "status_url": f"/event/check-in/{check_in.pk}/status/",
            "undo_url_template": f"/event/check-in/{check_in.pk}/records/__record_id__/undo/",
            "scan_count": check_in.scan_count,
            "scanner_config": {
                "scanUrl": f"/event/check-in/{check_in.pk}/scan/",
                "statusUrl": f"/event/check-in/{check_in.pk}/status/",
                "undoUrlTemplate": f"/event/check-in/{check_in.pk}/records/__record_id__/undo/",
                "csrfToken": get_token(request),
                "checkInId": str(check_in.pk),
                "isActive": check_in.is_active,
                "statusPollIntervalMs": 2000,
            },
            "change_url": reverse("admin:event_checkin_change", args=[check_in.pk]),
        }
        return TemplateResponse(request, "admin/event/checkin_scanner.html", context)


@admin.register(CheckInRecord)
class CheckInRecordAdmin(ReadOnlyModelAdmin):
    list_display = ("registration", "check_in", "scanned_by", "created_at")
    list_filter = ("check_in", "check_in__event")
    search_fields = (
        "registration__ticket_code",
        "registration__attendee_first_name",
        "registration__attendee_last_name",
    )
    ordering = ("-created_at",)

    def has_delete_permission(self, request, obj=None):
        return request.user.is_staff
