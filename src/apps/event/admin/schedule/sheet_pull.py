"""Pulling the current-project schedule from its Google Sheet: the sync actions, the Pull and auto-sync views."""

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import path, reverse
from unfold.decorators import action

from ...models import CurrentProjectSchedule
from ...services import ScheduleSyncError, sync_schedule


class ScheduleSheetPullMixin:
    """The Google Sheet sync actions and views of ``CurrentProjectScheduleAdmin``."""

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
        config = self._overview_schedule()
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
        config = self._overview_schedule()
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
