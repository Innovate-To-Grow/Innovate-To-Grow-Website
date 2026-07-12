from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.http import Http404
from unfold.admin import TabularInline
from unfold.decorators import display

from apps.core.admin import BaseModelAdmin
from apps.core.models import EmailServiceConfig, GoogleCredentialConfig

from ..models import Event, Question, Ticket
from ..services.copy_template import EventCopyTemplate, build_event_copy_template
from ..services.date_ranges import format_event_date_range

COPY_TEMPLATE_ATTR = "_event_admin_copy_template"
COPY_INLINE_INITIAL_ATTR = "_event_admin_copy_inline_initial"


class EventRelatedInlineMixin:
    """Delegate inline permissions to the registered Event ModelAdmin.

    Default Django inlines require ``event.add_ticket`` / ``change_ticket`` / etc.
    This project grants Event access via :class:`BaseModelAdmin` (typically ``is_staff``),
    so staff without those Ticket codenames would otherwise miss Tickets/Questions blocks.
    """

    def _event_model_admin(self):
        return self.admin_site._registry.get(Event)

    def has_view_permission(self, request, obj=None):
        ma = self._event_model_admin()
        if ma is None:
            return super().has_view_permission(request, obj)
        return ma.has_view_permission(request, obj)

    def has_add_permission(self, request, obj=None):
        ma = self._event_model_admin()
        if ma is None:
            return super().has_add_permission(request, obj)
        if obj is None:
            return ma.has_add_permission(request)
        return ma.has_change_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        ma = self._event_model_admin()
        if ma is None:
            return super().has_change_permission(request, obj)
        if obj is None:
            return ma.has_add_permission(request)
        return ma.has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        ma = self._event_model_admin()
        if ma is None:
            return super().has_delete_permission(request, obj)
        if obj is None:
            return ma.has_add_permission(request)
        return ma.has_change_permission(request, obj)

    def get_extra(self, request, obj=None, **kwargs):
        initial_by_model = getattr(request, COPY_INLINE_INITIAL_ATTR, {})
        if (obj is None or obj._state.adding) and self.model in initial_by_model:
            return len(initial_by_model[self.model])
        return super().get_extra(request, obj, **kwargs)


class TicketInline(EventRelatedInlineMixin, TabularInline):
    model = Ticket
    extra = 0
    fields = ("name", "order")


class QuestionInline(EventRelatedInlineMixin, TabularInline):
    model = Question
    extra = 0
    fields = ("text", "is_required", "order")


class EventAdminForm(forms.ModelForm):
    verify_phone_dependency_hint_id = "event-verify-phone-dependency-hint"

    class Meta:
        model = Event
        fields = "__all__"
        labels = {
            "allow_secondary_email": "Prompt for Second Email",
            "collect_phone": "Prompt for Phone Number",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if (
            not self.is_bound
            and not self.instance._state.adding
            and self.instance.end_date is None
            and self.instance.date is not None
        ):
            self.initial["end_date"] = self.instance.date
        widget = self.fields["verify_phone"].widget
        described_by = str(widget.attrs.get("aria-describedby") or "").split()
        if self.verify_phone_dependency_hint_id not in described_by:
            described_by.append(self.verify_phone_dependency_hint_id)
        widget.attrs["aria-describedby"] = " ".join(described_by)

    class Media:
        css = {"all": ("event/css/event_admin.css",)}
        js = ("event/js/event_admin.js",)


@admin.register(Event)
class EventAdmin(BaseModelAdmin):
    change_form_template = "admin/event/event/change_form.html"
    form = EventAdminForm
    list_display = (
        "name",
        "date_range",
        "location",
        "registration_open",
        "secondary_email_badge",
        "phone_badge",
    )
    list_filter = ("registration_open", "date", "end_date", "allow_secondary_email", "collect_phone")
    search_fields = ("name", "location")
    readonly_fields = (
        "created_at",
        "updated_at",
        "registration_sheet_synced_at",
        "registration_sheet_sync_count",
        "registration_sheet_sync_error",
    )
    prepopulated_fields = {"slug": ("name",)}
    inlines = [TicketInline, QuestionInline]

    fieldsets = (
        (
            "Event Details",
            {
                "fields": (
                    ("name", "slug"),
                    ("date", "end_date"),
                    "location",
                    "description",
                    "registration_open",
                ),
            },
        ),
        (
            "Registration Form Options",
            {
                "description": "Control which optional fields appear on the registration form.",
                "fields": (
                    "allow_secondary_email",
                    ("collect_phone", "verify_phone"),
                ),
            },
        ),
        (
            "Ticket Access Options",
            {
                "description": "Control the login link included in ticket confirmation emails.",
                "fields": (("ticket_login_validity_days", "ticket_login_reusable"),),
            },
        ),
        (
            "Registration Google Sheet",
            {
                "classes": ("collapse",),
                "description": "Link a Google Sheet to sync registration data for this event.",
                "fields": (
                    ("registration_sheet_id", "registration_sheet_gid"),
                    ("registration_sheet_synced_at", "registration_sheet_sync_count"),
                    "registration_sheet_sync_error",
                ),
            },
        ),
        (
            "System",
            {
                "classes": ("collapse",),
                "fields": (("created_at", "updated_at"),),
            },
        ),
    )

    @staticmethod
    def _get_site_settings_context():
        from apps.core.models import AWSCredentialConfig

        email_config = EmailServiceConfig.load()
        google_config = GoogleCredentialConfig.load()
        aws_config = AWSCredentialConfig.load()
        return {
            "email_config": email_config if email_config.pk else None,
            "google_config": google_config if google_config.pk else None,
            "google_configured": google_config.is_configured,
            "aws_config": aws_config if aws_config.pk else None,
        }

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = {**(extra_context or {}), **self._get_site_settings_context()}
        return super().change_view(request, object_id, form_url, extra_context)

    def add_view(self, request, form_url="", extra_context=None):
        copy_template = self._prepare_copy_template(request)
        copy_source_events = [
            {
                "pk": event.pk,
                "name": event.name,
                "date_range": format_event_date_range(event.date, event.effective_end_date),
            }
            for event in Event.objects.order_by("-date", "name")
        ]
        extra_context = {
            **(extra_context or {}),
            **self._get_site_settings_context(),
            "copy_template": copy_template,
            "copy_source_events": copy_source_events,
        }
        return super().add_view(request, form_url, extra_context)

    def _prepare_copy_template(self, request) -> EventCopyTemplate | None:
        if hasattr(request, COPY_TEMPLATE_ATTR):
            return getattr(request, COPY_TEMPLATE_ATTR)

        copy_template = None
        inline_initial = {}

        # ``copy_from`` is only a GET-time template selector. Once the browser
        # has loaded the snapshot, POSTed Event and inline values are the source
        # of truth. This also lets a reviewed form save if the source is deleted
        # in the meantime.
        if request.method == "GET":
            source_id = request.GET.get("copy_from", "").strip()
            if source_id:
                try:
                    source = Event.objects.prefetch_related("tickets", "questions").get(pk=source_id)
                except (Event.DoesNotExist, ValidationError, ValueError) as exc:
                    raise Http404("The Event selected as a copy source does not exist.") from exc

                copy_template = build_event_copy_template(source)
                inline_initial = {
                    Ticket: copy_template.ticket_initial(),
                    Question: copy_template.question_initial(),
                }

        setattr(request, COPY_TEMPLATE_ATTR, copy_template)
        setattr(request, COPY_INLINE_INITIAL_ATTR, inline_initial)
        return copy_template

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        copy_template = self._prepare_copy_template(request)
        if copy_template is None:
            return initial

        initial.update(copy_template.event_initial)
        return initial

    def get_formset_kwargs(self, request, obj, inline, prefix):
        kwargs = super().get_formset_kwargs(request, obj, inline, prefix)
        if request.method == "GET" and (obj is None or obj._state.adding):
            self._prepare_copy_template(request)
            initial_by_model = getattr(request, COPY_INLINE_INITIAL_ATTR, {})
            if inline.model in initial_by_model:
                kwargs["initial"] = initial_by_model[inline.model]
        return kwargs

    def get_confirmation_diff(self, request, obj, form, formsets, action_type):
        diff = super().get_confirmation_diff(request, obj, form, formsets, action_type)
        if action_type != "add":
            return diff

        formsets_by_model = {formset.model: formset for formset in formsets}
        ticket_rows = self._active_inline_rows(formsets_by_model.get(Ticket))
        question_rows = self._active_inline_rows(formsets_by_model.get(Question))

        if ticket_rows:
            ticket_rows.sort(key=lambda row: (row.get("order", 0), row.get("name", "")))
            diff.extend(
                {
                    "field": f"tickets.{index}",
                    "label": f"Ticket type {index}",
                    "new_value": f"{row['name']} — order {row.get('order', 0)}",
                }
                for index, row in enumerate(ticket_rows, start=1)
            )
        else:
            diff.append({"field": "tickets", "label": "Ticket types", "new_value": "None"})

        if question_rows:
            question_rows.sort(key=lambda row: (row.get("order", 0), row.get("text", "")))
            diff.extend(
                {
                    "field": f"questions.{index}",
                    "label": f"Question {index}",
                    "new_value": (
                        f"{row['text']} — required: {'Yes' if row.get('is_required') else 'No'}; "
                        f"order {row.get('order', 0)}"
                    ),
                }
                for index, row in enumerate(question_rows, start=1)
            )
        else:
            diff.append({"field": "questions", "label": "Questions", "new_value": "None"})

        return diff

    @staticmethod
    def _active_inline_rows(formset):
        if formset is None:
            return []
        rows = []
        for inline_form in formset.forms:
            cleaned_data = getattr(inline_form, "cleaned_data", None) or {}
            if cleaned_data.get("DELETE"):
                continue
            if inline_form.empty_permitted and not inline_form.has_changed():
                continue
            rows.append(cleaned_data)
        return rows

    @admin.action(description="Sync registrations to Google Sheet")
    def sync_registrations_to_sheet(self, request, queryset):
        from apps.event.services.registration_sheet_sync import RegistrationSyncError, sync_registrations_to_sheet

        for event in queryset:
            try:
                count = sync_registrations_to_sheet(event)
                messages.success(request, f'Synced {count} registrations for "{event.name}" to Google Sheet.')
            except RegistrationSyncError as exc:
                messages.error(request, f'Sync failed for "{event.name}": {exc}')

    actions = ["sync_registrations_to_sheet"]
    actions_no_confirmation = ["sync_registrations_to_sheet"]

    @display(description="Date range", ordering="date")
    def date_range(self, obj):
        return format_event_date_range(obj.date, obj.effective_end_date)

    @display(description="2nd Email", label={"on": "success", "off": "info"})
    def secondary_email_badge(self, obj):
        if obj.allow_secondary_email:
            return "on", "On"
        return "off", "Off"

    @display(
        description="Phone",
        label={"prompt_verify": "warning", "prompt": "success", "off": "info"},
    )
    def phone_badge(self, obj):
        if obj.collect_phone and obj.verify_phone:
            return "prompt_verify", "Prompt + verification"
        if obj.collect_phone:
            return "prompt", "Prompt"
        return "off", "Off"
