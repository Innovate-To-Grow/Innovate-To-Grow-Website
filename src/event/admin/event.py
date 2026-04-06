from django import forms
from django.contrib import admin, messages
from unfold.admin import TabularInline
from unfold.decorators import display

from core.admin import BaseModelAdmin
from core.models import EmailServiceConfig, GoogleCredentialConfig, SMSServiceConfig

from ..models import Event, Question, Ticket


class TicketInline(TabularInline):
    model = Ticket
    extra = 0
    fields = ("name", "order")


class QuestionInline(TabularInline):
    model = Question
    extra = 0
    fields = ("text", "is_required", "order")


class EventAdminForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = "__all__"
        labels = {
            "allow_secondary_email": "Prompt for Second Email",
        }


@admin.register(Event)
class EventAdmin(BaseModelAdmin):
    change_form_template = "admin/event/event/change_form.html"
    form = EventAdminForm
    list_display = (
        "name",
        "date",
        "location",
        "is_live",
        "secondary_email_badge",
        "phone_badge",
    )
    list_filter = ("is_live", "date", "allow_secondary_email", "collect_phone")
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
                "fields": ("name", "slug", "date", "location", "description", "is_live"),
            },
        ),
        (
            "Registration Form Options",
            {
                "description": "Control which optional fields appear on the registration form.",
                "fields": ("allow_secondary_email", "collect_phone", "verify_phone"),
            },
        ),
        (
            "Registration Google Sheet",
            {
                "classes": ("collapse",),
                "description": "Link a Google Sheet to sync registration data for this event.",
                "fields": (
                    "registration_sheet_id",
                    "registration_sheet_gid",
                    "registration_sheet_synced_at",
                    "registration_sheet_sync_count",
                    "registration_sheet_sync_error",
                ),
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

    @staticmethod
    def _get_site_settings_context():
        email_config = EmailServiceConfig.load()
        sms_config = SMSServiceConfig.load()
        google_config = GoogleCredentialConfig.load()
        return {
            "email_config": email_config if email_config.pk else None,
            "sms_config": sms_config if sms_config.pk else None,
            "google_config": google_config if google_config.pk else None,
            "google_configured": google_config.is_configured,
        }

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = {**(extra_context or {}), **self._get_site_settings_context()}
        return super().change_view(request, object_id, form_url, extra_context)

    def add_view(self, request, form_url="", extra_context=None):
        extra_context = {**(extra_context or {}), **self._get_site_settings_context()}
        return super().add_view(request, form_url, extra_context)

    @admin.action(description="Sync registrations to Google Sheet")
    def sync_registrations_to_sheet(self, request, queryset):
        from event.services.registration_sheet_sync import RegistrationSyncError, sync_registrations_to_sheet

        for event in queryset:
            try:
                count = sync_registrations_to_sheet(event)
                messages.success(request, f'Synced {count} registrations for "{event.name}" to Google Sheet.')
            except RegistrationSyncError as exc:
                messages.error(request, f'Sync failed for "{event.name}": {exc}')

    actions = ["sync_registrations_to_sheet"]

    @display(description="2nd Email", label=True)
    def secondary_email_badge(self, obj):
        if obj.allow_secondary_email:
            return "On", "success"
        return "Off", "info"

    @display(description="Phone", label=True)
    def phone_badge(self, obj):
        if obj.collect_phone and obj.verify_phone:
            return "Verified", "warning"
        if obj.collect_phone:
            return "Collect", "success"
        return "Off", "info"
