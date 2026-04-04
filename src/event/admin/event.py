from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import reverse
from unfold.admin import TabularInline
from unfold.decorators import action

from core.admin import BaseModelAdmin

from ..models import Event, Question, Ticket
from ..services import ScheduleSyncError, sync_event_schedule


class TicketInline(TabularInline):
    model = Ticket
    extra = 0
    fields = ("name", "order")


class QuestionInline(TabularInline):
    model = Question
    extra = 0
    fields = ("text", "is_required", "order")


@admin.register(Event)
class EventAdmin(BaseModelAdmin):
    list_display = ("name", "date", "location", "is_live", "schedule_last_synced_at")
    list_filter = ("is_live", "date")
    search_fields = ("name", "location")
    readonly_fields = ("created_at", "updated_at", "schedule_last_synced_at", "schedule_sync_error")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [TicketInline, QuestionInline]
    actions_detail = ["pull_schedule_from_google_sheets"]

    fieldsets = (
        (
            "Event Details",
            {
                "fields": ("name", "slug", "date", "location", "description", "is_live"),
            },
        ),
        (
            "Schedule Import",
            {
                "fields": (
                    "schedule_sheet_id",
                    "schedule_tracks_gid",
                    "schedule_projects_gid",
                    "schedule_last_synced_at",
                    "schedule_sync_error",
                ),
                "description": "Configure the Google Sheet source for this event schedule, then pull the latest data.",
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

    @action(description="Pull schedule from Google Sheets", url_path="pull-schedule", icon="sync")
    def pull_schedule_from_google_sheets(self, request, object_id):
        event = Event.objects.get(pk=object_id)
        try:
            stats = sync_event_schedule(event)
        except ScheduleSyncError as exc:
            messages.error(request, f"Schedule sync failed: {exc}")
        else:
            messages.success(
                request,
                (
                    f'Schedule synced for "{event.name}": '
                    f"{stats.sections_created} sections, "
                    f"{stats.tracks_created} tracks, "
                    f"{stats.slots_created} slots, "
                    f"{stats.unmatched_slots} unmatched, "
                    f"{stats.break_slots} breaks."
                ),
            )
        return HttpResponseRedirect(reverse("admin:event_event_change", args=[object_id]))
