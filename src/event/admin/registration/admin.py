import logging

from django.contrib import admin
from django.urls import path, reverse

from core.admin import BaseModelAdmin

from ...models import EventRegistration, Ticket
from .config import (
    ADD_FIELDSETS,
    ADD_READONLY_FIELDS,
    CHANGE_FIELDSETS,
    CHANGE_READONLY_FIELDS,
)
from .exports import RegistrationExportMixin
from .forms import EventRegistrationAdminForm
from .info_views import RegistrationInfoViewsMixin
from .ticket_emails import TicketEmailAdminMixin

logger = logging.getLogger(__name__)


@admin.register(EventRegistration)
class EventRegistrationAdmin(
    RegistrationExportMixin,
    TicketEmailAdminMixin,
    RegistrationInfoViewsMixin,
    BaseModelAdmin,
):
    form = EventRegistrationAdminForm
    change_list_template = "admin/event/eventregistration/change_list.html"
    export_filename = "event_registrations"

    class Media:
        js = ("event/js/registration_detail_panels.js",)

    list_display = (
        "ticket_code",
        "attendee_first_name",
        "attendee_last_name",
        "attendee_email",
        "attendee_secondary_email",
        "attendee_phone",
        "phone_verified",
        "ticket",
        "event",
        "created_at",
    )
    list_filter = ("event", "ticket")
    search_fields = (
        "attendee_first_name",
        "attendee_last_name",
        "attendee_email",
        "attendee_secondary_email",
        "attendee_phone",
        "attendee_organization",
        "ticket_code",
    )
    autocomplete_fields = ["member"]
    ordering = ("-created_at",)
    actions = ["resend_ticket_email"]

    def get_urls(self):
        custom = [
            path(
                "send-all-ticket-emails/",
                self.admin_site.admin_view(self.send_all_ticket_emails_view),
                name="event_eventregistration_send_all_ticket_emails",
            ),
            path(
                "member-info/<uuid:pk>/",
                self.admin_site.admin_view(self._member_info_view),
                name="reg-member-info",
            ),
            path(
                "event-info/<uuid:pk>/",
                self.admin_site.admin_view(self._event_info_view),
                name="reg-event-info",
            ),
        ]
        return custom + super().get_urls()

    def changelist_view(self, request, extra_context=None):
        extra_context = {
            **(extra_context or {}),
            "send_all_ticket_emails_url": reverse("admin:event_eventregistration_send_all_ticket_emails"),
        }
        return super().changelist_view(request, extra_context)

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return ADD_READONLY_FIELDS
        return CHANGE_READONLY_FIELDS

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return ADD_FIELDSETS
        return CHANGE_FIELDSETS

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "ticket":
            event_id = request.POST.get("event") or request.GET.get("event")
            if event_id:
                kwargs["queryset"] = Ticket.objects.filter(event_id=event_id)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

        try:
            from event.services.registration_sheet_sync import (
                schedule_registration_sync,
            )

            schedule_registration_sync(obj.event)
        except Exception:
            logger.exception("Sheet sync failed for registration %s", obj.pk)

        if form.cleaned_data.get("send_ticket_email"):
            try:
                from event.services.ticket_mail import send_ticket_email

                send_ticket_email(obj)
            except Exception:
                logger.exception("Failed to send ticket email for registration %s", obj.pk)

    # noinspection PyUnusedLocal,PyMethodMayBeStatic
    def has_add_permission(self, request):
        return True

    # noinspection PyUnusedLocal,PyMethodMayBeStatic
    def has_change_permission(self, request, obj=None):
        opts = self.model._meta
        return request.user.has_perm(f"{opts.app_label}.change_{opts.model_name}")

    # noinspection PyUnusedLocal,PyMethodMayBeStatic
    def has_delete_permission(self, request, obj=None):
        return True
