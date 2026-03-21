from django.contrib import admin
from unfold.admin import ModelAdmin

from ..models import EventRegistration


@admin.register(EventRegistration)
class EventRegistrationAdmin(ModelAdmin):
    list_display = (
        "event",
        "attendee_name",
        "attendee_email",
        "ticket",
        "ticket_code",
        "created_at",
        "ticket_email_sent_at",
    )
    list_filter = ("event", "ticket")
    search_fields = ("attendee_name", "attendee_email", "ticket_code")
    readonly_fields = (
        "member",
        "event",
        "ticket",
        "ticket_code",
        "attendee_name",
        "attendee_email",
        "question_answers",
        "ticket_email_sent_at",
        "ticket_email_error",
        "created_at",
        "updated_at",
    )
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return True
