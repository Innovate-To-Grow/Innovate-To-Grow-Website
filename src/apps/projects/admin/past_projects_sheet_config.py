from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import path, reverse

from apps.core.admin import BaseModelAdmin
from apps.core.models import GoogleCredentialConfig

from ..models import PastProjectsSheetConfig
from ..services.sheet_sync import SheetSyncError, format_sync_stats, sync_past_projects


@admin.register(PastProjectsSheetConfig)
class PastProjectsSheetConfigAdmin(BaseModelAdmin):
    list_display = ("name", "is_active", "last_synced_at", "sync_count", "sync_error_short", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "sheet_id", "worksheet_name")
    readonly_fields = ("last_synced_at", "sync_error", "sync_count", "created_at", "updated_at")
    change_list_template = "admin/projects/pastprojectssheetconfig_changelist.html"

    fieldsets = (
        (
            "Config",
            {
                "fields": ("name", "is_active"),
            },
        ),
        (
            "Google Sheet Source",
            {
                "fields": ("sheet_id", "worksheet_name"),
                "description": (
                    "Configure the Google Sheet and worksheet tab that holds past-project rows. "
                    "Share the sheet with the service-account email shown above (Viewer is enough)."
                ),
            },
        ),
        (
            "Auto Sync",
            {
                "fields": ("auto_sync_enabled", "sync_interval_minutes"),
                "description": (
                    "Enable auto-sync via cron. Schedule <code>python manage.py sync_past_projects</code> externally."
                ),
            },
        ),
        (
            "Sync Status",
            {
                "fields": ("last_synced_at", "sync_count", "sync_error"),
            },
        ),
        (
            "System",
            {
                "classes": ("collapse",),
                "fields": ("created_at", "updated_at"),
            },
        ),
    )

    @admin.display(description="Sync Error")
    def sync_error_short(self, obj):
        if obj.sync_error:
            return obj.sync_error[:80] + "..." if len(obj.sync_error) > 80 else obj.sync_error
        return ""

    def has_delete_permission(self, request, obj=None):
        return False

    def get_urls(self):
        custom_urls = [
            path(
                "pull/",
                self.admin_site.admin_view(self.pull_view),
                name="projects_pastprojectssheetconfig_pull",
            ),
            path(
                "save-sync-settings/",
                self.admin_site.admin_view(self.save_sync_settings_view),
                name="projects_pastprojectssheetconfig_save_sync_settings",
            ),
        ]
        return custom_urls + super().get_urls()

    def pull_view(self, request):
        # ``admin_view`` only enforces is_staff, so this custom URL must re-check
        # per-app access itself — otherwise a staff member without the projects app
        # could trigger a privileged Google Sheet sync here.
        if not self.has_change_permission(request):
            raise PermissionDenied("You do not have permission to sync past projects.")
        changelist_url = reverse("admin:projects_pastprojectssheetconfig_changelist")
        config = PastProjectsSheetConfig.load()
        if not config:
            messages.error(request, "No configuration found. Add one first.")
            return redirect(changelist_url)
        try:
            stats = sync_past_projects(config, sync_type="manual")
            messages.success(request, f"Synced: {format_sync_stats(stats)}")
        except SheetSyncError as exc:
            messages.error(request, f"Sync failed: {exc}")
        return redirect(changelist_url)

    def save_sync_settings_view(self, request):
        # ``admin_view`` only enforces is_staff, so this custom URL must re-check
        # per-app access itself — otherwise a staff member without the projects app
        # could change the auto-sync configuration here.
        if not self.has_change_permission(request):
            raise PermissionDenied("You do not have permission to change sync settings.")
        changelist_url = reverse("admin:projects_pastprojectssheetconfig_changelist")
        if request.method != "POST":
            return redirect(changelist_url)
        config = PastProjectsSheetConfig.load()
        if not config:
            messages.error(request, "No active configuration to update.")
            return redirect(changelist_url)
        config.auto_sync_enabled = request.POST.get("auto_sync_enabled") == "1"
        try:
            interval = int(request.POST.get("sync_interval_minutes", 1440))
            config.sync_interval_minutes = max(1, min(10080, interval))  # cap at 1 week
        except (ValueError, TypeError):
            pass
        config.save(update_fields=["auto_sync_enabled", "sync_interval_minutes", "updated_at"])
        messages.success(request, "Auto-sync settings saved.")
        return redirect(changelist_url)

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        google_config = GoogleCredentialConfig.load()
        extra_context["google_configured"] = google_config.is_configured
        extra_context["google_project_id"] = google_config.project_id
        extra_context["google_client_email"] = google_config.client_email
        config = PastProjectsSheetConfig.load()
        extra_context["config"] = config
        extra_context["pull_url"] = reverse("admin:projects_pastprojectssheetconfig_pull")
        extra_context["save_sync_settings_url"] = reverse("admin:projects_pastprojectssheetconfig_save_sync_settings")
        return super().changelist_view(request, extra_context=extra_context)
