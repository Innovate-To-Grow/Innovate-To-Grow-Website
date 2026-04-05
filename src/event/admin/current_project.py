from django.contrib import admin, messages
from django.shortcuts import redirect
from django.urls import path, reverse

from core.admin import BaseModelAdmin
from core.models import GoogleCredentialConfig

from ..models import CurrentProjectSchedule, Event
from ..services import ScheduleSyncError, sync_event_schedule


@admin.register(CurrentProjectSchedule)
class CurrentProjectScheduleAdmin(BaseModelAdmin):
    list_display = ("__str__", "last_synced_at", "sync_error_short")
    readonly_fields = ("last_synced_at", "sync_error", "created_at", "updated_at")
    change_list_template = "admin/event/currentprojectschedule_changelist.html"

    fieldsets = (
        (
            "Google Sheet Source",
            {
                "fields": ("sheet_id", "tracks_gid", "projects_gid"),
                "description": "Configure the Google Sheet that contains current project and schedule data.",
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

    def has_add_permission(self, request):
        if CurrentProjectSchedule.objects.exists():
            return False
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False

    def get_urls(self):
        custom_urls = [
            path(
                "pull/",
                self.admin_site.admin_view(self.pull_view),
                name="event_currentprojectschedule_pull",
            ),
        ]
        return custom_urls + super().get_urls()

    def pull_view(self, request):
        changelist_url = reverse("admin:event_currentprojectschedule_changelist")
        live_event = Event.objects.filter(is_live=True).first()
        if not live_event:
            messages.error(request, "No live event found. Create an event and set it as live first.")
            return redirect(changelist_url)
        try:
            stats = sync_event_schedule(live_event)
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

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}

        google_config = GoogleCredentialConfig.load()
        extra_context["google_configured"] = google_config.is_configured
        extra_context["google_project_id"] = google_config.project_id
        extra_context["google_client_email"] = google_config.client_email

        config = CurrentProjectSchedule.load()
        extra_context["config"] = config if config.pk else None
        extra_context["pull_url"] = reverse("admin:event_currentprojectschedule_pull")

        # Current projects (newest published semester)
        from projects.models import Project, Semester

        newest = Semester.objects.filter(is_published=True).first()
        extra_context["current_semester"] = newest
        if newest:
            extra_context["current_projects"] = Project.objects.filter(semester=newest).order_by(
                "class_code", "team_number"
            )
        else:
            extra_context["current_projects"] = []

        # Winners from schedule tracks (live event)
        from event.models import EventScheduleTrack

        live_event = Event.objects.filter(is_live=True).first()
        if live_event:
            winners = (
                EventScheduleTrack.objects.filter(section__event=live_event)
                .exclude(winner="")
                .select_related("section")
                .order_by("section__display_order", "display_order")
            )
            extra_context["winners"] = winners
        else:
            extra_context["winners"] = []

        return super().changelist_view(request, extra_context=extra_context)
