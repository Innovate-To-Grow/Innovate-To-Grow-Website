from django.contrib import admin
from django.utils.html import format_html

from apps.core.admin import BaseModelAdmin, ReadOnlyModelAdmin

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
        (None, {"fields": ("is_enabled", "auto_sync_enabled", "google_sheet_id", "worksheet_gid")}),
        ("Sync State", {"fields": ("synced_at", "sync_count", "sync_error"), "classes": ("collapse",)}),
    )
    readonly_fields = ("synced_at", "sync_count", "sync_error")

    @admin.display(description="Last Error")
    def sync_error_short(self, obj):
        if not obj.sync_error:
            return ""
        truncated = obj.sync_error[:80]
        return format_html('<span title="{}">{}</span>', obj.sync_error, truncated)


@admin.register(MemberSheetSyncLog)
class MemberSheetSyncLogAdmin(ReadOnlyModelAdmin):
    list_display = ("created_at", "sync_type", "status_badge", "rows_written", "error_message_short")
    list_filter = ("sync_type", "status")
    ordering = ("-created_at",)

    @admin.display(description="Status")
    def status_badge(self, obj):
        # Render as a white-on-saturated-background pill rather than colored
        # text. A single text color cannot satisfy contrast on BOTH the
        # near-white light surface (#fffbfb) and the near-black dark surface
        # (#131314): the old CSS "green" (#008000) failed dark, while plain
        # #10b981 text fails AA on light (~2.5:1). White text on a filled
        # saturated background reads on either surface — the same mode-safe
        # pattern AdminInvitationAdmin.status_badge uses.
        background = "#10b981" if obj.status == MemberSheetSyncLog.Status.SUCCESS else "#ef4444"
        return format_html(
            '<span style="display:inline-block;padding:2px 10px;border-radius:12px;'
            'font-size:12px;font-weight:600;color:#fff;background:{};">{}</span>',
            background,
            obj.get_status_display(),
        )

    @admin.display(description="Error")
    def error_message_short(self, obj):
        if not obj.error_message:
            return ""
        return obj.error_message[:100]
