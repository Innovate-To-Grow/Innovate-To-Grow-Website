"""The current-project schedule admin: the schedule row, its Google Sheet link, and the changelist overview."""

from urllib.parse import quote

from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from apps.core.admin import BaseModelAdmin
from apps.core.models import GoogleCredentialConfig

from ...models import CurrentProjectSchedule, EventScheduleTrack
from .agenda import EventAgendaItemInline
from .sheet_pull import ScheduleSheetPullMixin

SHEET_LINK_FIELD = "google_sheet_link"


def google_sheet_url(sheet_id):
    """The sheet's edit page, as the registration sheet-sync page links its spreadsheet (the id is URL-quoted)."""
    return f"https://docs.google.com/spreadsheets/d/{quote(sheet_id, safe='')}/edit"


def _with_sheet_link(options):
    """A copy of a fieldset's options with the sheet button right after ``sheet_id``; other fieldsets unchanged."""
    fields = list(options.get("fields", ()))
    if "sheet_id" not in fields:
        return options
    fields.insert(fields.index("sheet_id") + 1, SHEET_LINK_FIELD)
    return {**options, "fields": tuple(fields)}


@admin.register(CurrentProjectSchedule)
class CurrentProjectScheduleAdmin(ScheduleSheetPullMixin, BaseModelAdmin):
    list_display = ("name", "is_active", "last_synced_at", "sync_error_short", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "sheet_id")
    readonly_fields = (SHEET_LINK_FIELD, "last_synced_at", "sync_error", "created_at", "updated_at")
    change_list_template = "admin/event/currentprojectschedule/change_list.html"
    # Each schedule row (e.g. one per event year) has its own Google Sheet, so
    # every row — not only the active one — can be pulled from the changelist
    # and from its change form. The "Pull" object-tool above the list stays
    # scoped to the overview schedule (see ``_overview_schedule``).
    actions_row = ["sync_from_google_sheets"]
    actions_detail = ["sync_from_google_sheets_detail"]
    inlines = [EventAgendaItemInline]

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

    def get_fieldsets(self, request, obj=None):
        """Show the Open Google Sheet button under the Sheet ID of a saved row that has one; otherwise nothing."""
        fieldsets = super().get_fieldsets(request, obj)
        if obj is None or obj._state.adding or not (obj.sheet_id or "").strip():
            return fieldsets
        return tuple((name, _with_sheet_link(options)) for name, options in fieldsets)

    @admin.display(description="Google Sheet")
    def google_sheet_link(self, obj):
        return format_html(
            '<a class="i2g-admin-action" href="{}" target="_blank" rel="noopener noreferrer">'
            '<span class="material-symbols-outlined">open_in_new</span>Open Google Sheet</a>',
            google_sheet_url(obj.sheet_id.strip()),
        )

    @admin.display(description="Sync Error")
    def sync_error_short(self, obj):
        if obj.sync_error:
            return obj.sync_error[:80] + "..." if len(obj.sync_error) > 80 else obj.sync_error
        return ""

    def has_delete_permission(self, request, obj=None):
        return False

    def _overview_schedule(self):
        """The schedule the changelist overview (cards, Pull, Auto Sync) acts on.

        With several rows only the active one qualifies. With a single row it
        is shown even when it is not active, so a schedule that has not been
        activated yet is not hidden behind an empty overview.
        """
        config = CurrentProjectSchedule.load()
        if config is not None:
            return config
        rows = list(CurrentProjectSchedule.objects.all()[:2])
        return rows[0] if len(rows) == 1 else None

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}

        google_config = GoogleCredentialConfig.load()
        extra_context["google_configured"] = google_config.is_configured
        extra_context["google_project_id"] = google_config.project_id
        extra_context["google_client_email"] = google_config.client_email

        config = self._overview_schedule()
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
