from django.contrib import admin, messages
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html

from core.admin import BaseModelAdmin, ReadOnlyModelAdmin

from ..models import MemberSheetSyncConfig, MemberSheetSyncLog


@admin.register(MemberSheetSyncConfig)
class MemberSheetSyncConfigAdmin(BaseModelAdmin):
    list_display = (
        "__str__",
        "is_enabled",
        "auto_sync_enabled",
        "google_sheet_id",
        "synced_at",
        "sync_count",
        "sync_error_short",
    )
    list_filter = ("is_enabled", "auto_sync_enabled")
    fieldsets = (
        (None, {"fields": ("is_enabled", "google_sheet_id", "worksheet_gid")}),
        ("Sync State", {"fields": ("synced_at", "sync_count", "sync_error"), "classes": ("collapse",)}),
    )
    readonly_fields = ("synced_at", "sync_count", "sync_error")

    @admin.display(description="Last Error")
    def sync_error_short(self, obj):
        if not obj.sync_error:
            return ""
        truncated = obj.sync_error[:80]
        return format_html('<span title="{}">{}</span>', obj.sync_error, truncated)

    def get_urls(self):
        custom_urls = [
            path(
                "sync-settings/",
                self.admin_site.admin_view(self.sync_settings_view),
                name="authn_membersheetsyncconfig_sync_settings",
            ),
        ]
        return custom_urls + super().get_urls()

    def sync_settings_view(self, request):
        changelist_url = reverse("admin:authn_membersheetsyncconfig_changelist")
        config = MemberSheetSyncConfig.load()
        if not config.pk:
            messages.error(request, "No configuration found. Create one first via the Sync Config tab.")
            return redirect(changelist_url)

        if request.method == "POST":
            config.auto_sync_enabled = request.POST.get("auto_sync_enabled") == "1"
            config.save(update_fields=["auto_sync_enabled", "updated_at"])
            messages.success(request, "Auto-sync settings saved.")
            return redirect(reverse("admin:authn_membersheetsyncconfig_sync_settings"))

        context = {
            **self.admin_site.each_context(request),
            "title": "Auto Sync Settings",
            "config": config,
            "opts": self.model._meta,
            "changelist_url": changelist_url,
        }
        return TemplateResponse(request, "admin/authn/membersheetsyncconfig_sync_settings.html", context)


@admin.register(MemberSheetSyncLog)
class MemberSheetSyncLogAdmin(ReadOnlyModelAdmin):
    list_display = ("created_at", "sync_type", "status_badge", "rows_written", "error_message_short")
    list_filter = ("sync_type", "status")
    ordering = ("-created_at",)

    @admin.display(description="Status")
    def status_badge(self, obj):
        color = "green" if obj.status == MemberSheetSyncLog.Status.SUCCESS else "red"
        return format_html('<span style="color: {};">{}</span>', color, obj.get_status_display())

    @admin.display(description="Error")
    def error_message_short(self, obj):
        if not obj.error_message:
            return ""
        return obj.error_message[:100]
