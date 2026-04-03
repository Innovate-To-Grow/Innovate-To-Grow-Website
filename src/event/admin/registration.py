from django.contrib import admin

from core.admin import BaseModelAdmin

from ..models import EventRegistration


@admin.register(EventRegistration)
class EventRegistrationAdmin(BaseModelAdmin):
    list_display = (
        "event",
        "attendee_first_name",
        "attendee_last_name",
        "attendee_email",
        "attendee_organization",
        "ticket",
        "ticket_code",
        "created_at",
        "ticket_email_sent_at",
    )
    list_filter = ("event", "ticket")
    search_fields = (
        "attendee_first_name",
        "attendee_last_name",
        "attendee_email",
        "attendee_organization",
        "ticket_code",
    )
    readonly_fields = (
        "member",
        "event",
        "ticket",
        "ticket_code",
        "attendee_first_name",
        "attendee_last_name",
        "attendee_email",
        "attendee_organization",
        "question_answers",
        "ticket_email_sent_at",
        "ticket_email_error",
        "created_at",
        "updated_at",
    )
    ordering = ("-created_at",)

    # noinspection PyUnusedLocal,PyMethodMayBeStatic
    def has_add_permission(self, request):
        return False

    # noinspection PyUnusedLocal,PyMethodMayBeStatic
    def has_change_permission(self, request, obj=None):
        return False

    # noinspection PyUnusedLocal,PyMethodMayBeStatic
    def has_delete_permission(self, request, obj=None):
        return True
