from django.contrib import admin, messages
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse

from core.admin import BaseModelAdmin
from core.models import GoogleCredentialConfig

from ..models import CurrentProject, CurrentProjectSchedule, EventScheduleTrack
from ..services import ScheduleSyncError, sync_schedule


@admin.register(CurrentProject)
class CurrentProjectAdmin(BaseModelAdmin):
    list_display = (
        "class_code",
        "team_number",
        "team_name",
        "project_title",
        "organization",
        "is_presenting",
        "schedule",
    )
    list_editable = ("is_presenting",)
    list_filter = ("is_presenting", "class_code", "schedule")
    search_fields = ("team_number", "team_name", "project_title", "organization")
    list_per_page = 200

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CurrentProjectSchedule)
class CurrentProjectScheduleAdmin(BaseModelAdmin):
    list_display = ("name", "is_active", "last_synced_at", "sync_error_short", "created_at")
    list_filter = ("is_active",)
    readonly_fields = ("last_synced_at", "sync_error", "created_at", "updated_at")
    change_list_template = "admin/event/currentprojectschedule_changelist.html"

    fieldsets = (
        (
            "Event",
            {
                "fields": ("name", "is_active", "show_winners"),
            },
        ),
        (
            "Google Sheet Source",
            {
                "fields": ("sheet_id", "tracks_gid", "projects_gid"),
                "description": "Configure the Google Sheet that contains current project and schedule data.",
            },
        ),
        (
            "Auto Sync",
            {
                "fields": ("auto_sync_enabled", "sync_interval_minutes"),
                "description": (
                    "Enable automatic syncing via cron. "
                    "Run <code>python manage.py sync_schedule</code> every few minutes."
                ),
            },
        ),
        (
            "Sync Status",
            {
                "fields": ("last_synced_at", "sync_error"),
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
                name="event_currentprojectschedule_pull",
            ),
            path(
                "sync-settings/",
                self.admin_site.admin_view(self.sync_settings_view),
                name="event_currentprojectschedule_sync_settings",
            ),
        ]
        return custom_urls + super().get_urls()

    def pull_view(self, request):
        changelist_url = reverse("admin:event_currentprojectschedule_changelist")
        config = CurrentProjectSchedule.load()
        if not config:
            messages.error(request, "No configuration found. Add one first.")
            return redirect(changelist_url)
        try:
            stats = sync_schedule(config)
            messages.success(
                request,
                (
                    f"Synced: {stats.sections_created} sections, "
                    f"{stats.tracks_created} tracks, "
                    f"{stats.slots_created} slots, "
                    f"{stats.unmatched_slots} unmatched."
                ),
            )
        except ScheduleSyncError as exc:
            messages.error(request, f"Sync failed: {exc}")
        return redirect(changelist_url)

    def sync_settings_view(self, request):
        changelist_url = reverse("admin:event_currentprojectschedule_changelist")
        config = CurrentProjectSchedule.load()
        if not config:
            messages.error(request, "No active configuration to update.")
            return redirect(changelist_url)

        if request.method == "POST":
            config.auto_sync_enabled = request.POST.get("auto_sync_enabled") == "1"
            try:
                interval = int(request.POST.get("sync_interval_minutes", 60))
                config.sync_interval_minutes = max(1, interval)
            except (ValueError, TypeError):
                pass
            config.save(update_fields=["auto_sync_enabled", "sync_interval_minutes", "updated_at"])
            messages.success(request, "Auto-sync settings saved.")
            return redirect(reverse("admin:event_currentprojectschedule_sync_settings"))

        context = {
            **self.admin_site.each_context(request),
            "title": "Sync Settings",
            "config": config,
            "opts": self.model._meta,
            "changelist_url": changelist_url,
        }
        return TemplateResponse(request, "admin/event/currentprojectschedule_sync_settings.html", context)

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}

        google_config = GoogleCredentialConfig.load()
        extra_context["google_configured"] = google_config.is_configured
        extra_context["google_project_id"] = google_config.project_id
        extra_context["google_client_email"] = google_config.client_email

        config = CurrentProjectSchedule.load()
        extra_context["config"] = config
        extra_context["pull_url"] = reverse("admin:event_currentprojectschedule_pull")
        extra_context["sync_settings_url"] = reverse("admin:event_currentprojectschedule_sync_settings")

        if config:
            extra_context["current_schedule_name"] = config.name
            extra_context["current_projects"] = config.projects.order_by("class_code", "team_number")
        else:
            extra_context["current_schedule_name"] = ""
            extra_context["current_projects"] = []

        if config:
            winners = (
                EventScheduleTrack.objects.filter(section__config=config)
                .exclude(winner="")
                .select_related("section")
                .order_by("section__display_order", "display_order")
            )
            extra_context["winners"] = winners
        else:
            extra_context["winners"] = []

        return super().changelist_view(request, extra_context=extra_context)
