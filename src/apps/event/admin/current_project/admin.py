from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import F, Max
from django.forms import BaseInlineFormSet
from django.shortcuts import redirect
from django.urls import path, reverse
from unfold.admin import TabularInline
from unfold.decorators import action

from apps.core.admin import AppAccessInlineMixin, BaseModelAdmin
from apps.core.models import GoogleCredentialConfig

from ...models import CurrentProject, CurrentProjectSchedule, EventAgendaItem, EventScheduleTrack
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


MAX_DISPLAY_ORDER = 9999
ORDER_KEY_FIELDS = {"section_type", "display_order"}


class EventAgendaItemForm(forms.ModelForm):
    class Meta:
        model = EventAgendaItem
        fields = ("section_type", "display_order", "time_label", "title", "location")
        help_texts = {
            "section_type": "Expo fills the “EXPO: POSTERS AND DEMOS” table; Awards fills “AWARDS & RECEPTION”.",
            "display_order": "Row order within its table, lowest first. Leave blank on a new row to add it at the end.",
            "location": "The table's “Room:” header shows the location of its first row.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance._state.adding:
            order = self.fields["display_order"]
            order.required = False
            order.widget.attrs["placeholder"] = "end"
            # A blank first choice (the model field has none), so a row nobody touched is not "changed" and is ignored.
            section_type = self.fields["section_type"]
            section_type.choices = [("", "---------"), *section_type.choices]

    def clean_display_order(self):
        order = self.cleaned_data["display_order"]
        # Only a value being entered is capped, so an older row above the cap stays editable.
        if order is not None and order > MAX_DISPLAY_ORDER and "display_order" in self.changed_data:
            raise forms.ValidationError(f"Use a number up to {MAX_DISPLAY_ORDER}.")
        return order


class EventAgendaItemFormSet(BaseInlineFormSet):
    """Order rows by ``display_order`` — unique per (schedule, table) — without the editor juggling numbers.

    * A new row left blank is appended after the last one, in the order the rows were entered.
    * Rows may be swapped, shifted or moved between tables in one save. The unique constraint is checked row by
      row while saving, so the rows being rewritten are first moved out of the way (see ``save_existing_objects``).
    * A new or moved row that lands on an order held by a row this page never loaded (another editor added it
      since) is reported as a form error instead of failing at the database. Two saves that commit in the same
      instant can still collide; that surfaces as a server error and the editor just saves again.
    """

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        if index is None or index >= self.initial_form_count():
            # Blank, not the model default of 0 — which would clash with the first row (see ``clean``).
            kwargs["initial"] = {**kwargs.get("initial", {}), "display_order": None}
        return kwargs

    def _live_forms(self):
        """Forms that will leave a row behind: filled in, valid and not marked for deletion."""
        return [
            form for form in self.forms if form.is_valid() and form.cleaned_data and not self._should_delete_form(form)
        ]

    def clean(self):
        live = self._live_forms()
        moving = [form for form in live if form.instance._state.adding or ORDER_KEY_FIELDS & set(form.changed_data)]
        if moving:
            held_elsewhere = self._orders_held_outside_submission()
            self._append_blank_orders(live, held_elsewhere)
            for form in moving:
                if (form.cleaned_data["section_type"], form.cleaned_data["display_order"]) in held_elsewhere:
                    form.add_error("display_order", "Another row of this table already uses this display order.")
        self._flag_rows_sharing_an_order(live)

    @staticmethod
    def _flag_rows_sharing_an_order(live):
        """Report rows of one table with the same order.

        Django's own check skips rows marked for deletion only while the whole formset is valid, so it
        would blame a row that is about to be deleted as soon as any other row has an error.
        """
        rows_by_key = {}
        for form in live:
            if "display_order" in form.cleaned_data:  # gone if the check above already rejected this row
                key = (form.cleaned_data["section_type"], form.cleaned_data["display_order"])
                rows_by_key.setdefault(key, []).append(form)
        for forms_sharing in rows_by_key.values():
            if len(forms_sharing) > 1:
                for form in forms_sharing:
                    form.add_error("display_order", "Two rows of the same table share a display order.")

    def _orders_held_outside_submission(self):
        if self.instance._state.adding:
            return set()
        submitted = [form.instance.pk for form in self.initial_forms]
        rows = EventAgendaItem.objects.filter(config=self.instance).exclude(pk__in=submitted)
        return set(rows.values_list("section_type", "display_order"))

    @staticmethod
    def _append_blank_orders(live, held_elsewhere):
        taken = [order for _, order in held_elsewhere]
        taken += [form.cleaned_data["display_order"] for form in live if form.cleaned_data["display_order"] is not None]
        next_order = max(taken, default=-1) + 1
        for form in live:
            if form.cleaned_data["display_order"] is None:
                form.cleaned_data["display_order"] = form.instance.display_order = next_order
                next_order += 1

    def save_existing_objects(self, commit=True):
        if commit:
            rewritten = [
                form.instance.pk
                for form in self.initial_forms
                if self._should_delete_form(form) or ORDER_KEY_FIELDS & set(form.changed_data)
            ]
            if rewritten:
                # Park above every order that exists or is about to be written, so a parked row can never
                # meet another row's final order while the rest are rewritten.
                top = EventAgendaItem.objects.filter(config=self.instance).aggregate(top=Max("display_order"))["top"]
                finals = [form.cleaned_data["display_order"] for form in self._live_forms()]
                offset = max([top or 0, *finals]) + 1
                EventAgendaItem.objects.filter(pk__in=rewritten).update(display_order=F("display_order") + offset)
        return super().save_existing_objects(commit)


class EventAgendaItemInline(AppAccessInlineMixin, TabularInline):
    """The Expo / Awards tables on the schedule page — text the Google Sheet does not carry.

    Editing here is permanent: ``sync_schedule`` seeds these rows once (first sync) and never rewrites them.
    Deleting rows stays allowed although the schedule admin itself cannot be deleted.
    """

    model = EventAgendaItem
    form = EventAgendaItemForm
    formset = EventAgendaItemFormSet
    extra = 0
    ordering = ("section_type", "display_order")
    verbose_name = "Agenda item"
    verbose_name_plural = "Agenda items (Expo and Awards tables on the schedule page)"


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
