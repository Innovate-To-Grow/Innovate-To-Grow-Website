from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import path, reverse
from unfold.decorators import action

from apps.core.admin import BaseModelAdmin
from apps.core.models import GoogleCredentialConfig

from ...models import CurrentProject, CurrentProjectSchedule, EventScheduleTrack
from ...services import ScheduleSyncError, sync_schedule


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
    search_fields = ("name", "sheet_id")
    readonly_fields = ("last_synced_at", "sync_error", "created_at", "updated_at")
    change_list_template = "admin/event/currentprojectschedule/change_list.html"
    # Each schedule row (e.g. one per event year) has its own Google Sheet, so
    # every row — not only the active one — can be pulled from the changelist
    # and from its change form. The "Pull" object-tool above the list stays
    # scoped to the active schedule.
    actions_row = ["sync_from_google_sheets"]
    actions_detail = ["sync_from_google_sheets_detail"]

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

    # ``permissions=["change"]`` makes Unfold call ``has_change_permission``
    # before the view runs, so per-app access is enforced like the custom views.
    @action(
        description="Sync from Google Sheets",
        url_path="sync-from-google-sheets",
        icon="sync",
        permissions=["change"],
    )
    def sync_from_google_sheets(self, request, object_id):
        """Changelist row action: sync this row and return to the list."""
        changelist_url = reverse("admin:event_currentprojectschedule_changelist")
        self._sync_by_object_id(request, object_id)
        return redirect(changelist_url)

    @action(
        description="Sync from Google Sheets",
        url_path="sync-from-google-sheets-detail",
        icon="sync",
        permissions=["change"],
    )
    def sync_from_google_sheets_detail(self, request, object_id):
        """Change-form action: sync this row and stay on its change form."""
        config = self._sync_by_object_id(request, object_id)
        if config is None:
            return redirect(reverse("admin:event_currentprojectschedule_changelist"))
        return redirect(reverse("admin:event_currentprojectschedule_change", args=[config.pk]))

    def _sync_by_object_id(self, request, object_id):
        config = CurrentProjectSchedule.load_by_id(object_id)
        if config is None:
            messages.error(request, "Schedule not found.")
            return None
        self._run_sync(request, config)
        return config

    def _run_sync(self, request, config):
        try:
            stats = sync_schedule(config, sync_type="manual")
        except ScheduleSyncError as exc:
            messages.error(request, f"Sync failed for '{config}': {exc}")
            return
        messages.success(request, f"Synced '{config}': {stats.summary()}")

    def get_urls(self):
        custom_urls = [
            path(
                "pull/",
                self.admin_site.admin_view(self.pull_view),
                name="event_currentprojectschedule_pull",
            ),
            path(
                "save-sync-settings/",
                self.admin_site.admin_view(self.save_sync_settings_view),
                name="event_currentprojectschedule_save_sync_settings",
            ),
        ]
        return custom_urls + super().get_urls()

    def pull_view(self, request):
        # ``admin_view`` only enforces is_staff; re-check per-app access so a
        # staff member without the event app cannot trigger a schedule sync.
        if not self.has_change_permission(request):
            raise PermissionDenied("You do not have permission to sync the schedule.")
        changelist_url = reverse("admin:event_currentprojectschedule_changelist")
        config = CurrentProjectSchedule.load()
        if not config:
            messages.error(request, "No configuration found. Add one first.")
            return redirect(changelist_url)
        self._run_sync(request, config)
        return redirect(changelist_url)

    def save_sync_settings_view(self, request):
        # ``admin_view`` only enforces is_staff; re-check per-app access so a
        # staff member without the event app cannot change auto-sync settings.
        if not self.has_change_permission(request):
            raise PermissionDenied("You do not have permission to change sync settings.")
        changelist_url = reverse("admin:event_currentprojectschedule_changelist")
        if request.method != "POST":
            return redirect(changelist_url)
        config = CurrentProjectSchedule.load()
        if not config:
            messages.error(request, "No active configuration to update.")
            return redirect(changelist_url)
        config.auto_sync_enabled = request.POST.get("auto_sync_enabled") == "1"
        try:
            interval = int(request.POST.get("sync_interval_minutes", 60))
            config.sync_interval_minutes = max(1, min(1440, interval))
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

        config = CurrentProjectSchedule.load()
        extra_context["config"] = config
        extra_context["pull_url"] = reverse("admin:event_currentprojectschedule_pull")
        extra_context["save_sync_settings_url"] = reverse("admin:event_currentprojectschedule_save_sync_settings")

        if config:
            all_projects = list(config.projects.order_by("class_code", "team_number"))
            extra_context["current_schedule_name"] = config.name
            extra_context["current_projects"] = [p for p in all_projects if p.is_presenting]
            extra_context["non_presenting_projects"] = [p for p in all_projects if not p.is_presenting]
        else:
            extra_context["current_schedule_name"] = ""
            extra_context["current_projects"] = []
            extra_context["non_presenting_projects"] = []

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
