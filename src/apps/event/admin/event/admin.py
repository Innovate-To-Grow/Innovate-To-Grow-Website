from django.contrib import admin, messages
from unfold.decorators import display

from apps.core.admin import BaseModelAdmin

from ...models import Event
from ...services.ticket.date_ranges import format_event_date_range
from ..registration_sheet.controls import RegistrationSheetSyncAdminMixin
from .confirmation import EventConfirmationMixin
from .copy_template import EventCopyTemplateMixin
from .forms import EventAdminForm
from .inlines import QuestionInline, TicketInline


@admin.register(Event)
class EventAdmin(EventCopyTemplateMixin, EventConfirmationMixin, RegistrationSheetSyncAdminMixin, BaseModelAdmin):
    change_form_template = "admin/event/event/change_form.html"
    form = EventAdminForm
    list_display = (
        "name",
        "date_range",
        "location",
        "registration_open",
        "secondary_email_badge",
        "phone_badge",
        "sheet_sync_link",
    )
    list_filter = ("registration_open", "date", "end_date", "allow_secondary_email", "collect_phone")
    search_fields = ("name", "location")
    readonly_fields = (
        "created_at",
        "updated_at",
        "registration_sheet_synced_at",
        "registration_sheet_sync_count",
        "registration_sheet_sync_error",
        "registration_sheet_management",
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
            "Phone Number",
            {
                "description": "Choose whether to collect, verify, and require a phone number.",
                "fields": ("collect_phone", "verify_phone", "require_phone"),
            },
        ),
        (
            "Secondary Email",
            {
                "description": "Choose whether to collect, verify, and require a secondary email address.",
                "fields": ("allow_secondary_email", "verify_secondary_email", "require_secondary_email"),
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
                "description": "Manage the connection, timing, and exported columns on the dedicated sync page.",
                "fields": ("registration_sheet_management",),
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

    @staticmethod
    def _contact_badge(collect, verify, required):
        if not collect:
            return "off", "Off"
        label = "Required" if required else "Optional"
        return ("verify", f"{label} + verification") if verify else ("collect", label)

    @display(description="Secondary Email", label={"verify": "warning", "collect": "success", "off": "info"})
    def secondary_email_badge(self, obj):
        return self._contact_badge(obj.allow_secondary_email, obj.verify_secondary_email, obj.require_secondary_email)

    @display(
        description="Phone",
        label={"verify": "warning", "collect": "success", "off": "info"},
    )
    def phone_badge(self, obj):
        return self._contact_badge(obj.collect_phone, obj.verify_phone, obj.require_phone)
