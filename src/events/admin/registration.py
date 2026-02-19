"""
Admin interface for Event registration models.
"""

from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from ..models import (
    EventQuestion,
    EventRegistration,
    EventRegistrationAnswer,
    EventTicketOption,
)


@admin.register(EventTicketOption)
class EventTicketOptionAdmin(ModelAdmin):
    """Admin interface for event ticket options."""

    list_display = ("label", "event", "order", "is_active", "updated_at")
    list_filter = ("event", "is_active")
    list_editable = ("order", "is_active")
    search_fields = ("label", "event__event_name")
    ordering = ("event", "order", "id")


@admin.register(EventQuestion)
class EventQuestionAdmin(ModelAdmin):
    """Admin interface for event registration questions."""

    list_display = ("prompt", "event", "order", "required", "is_active", "updated_at")
    list_filter = ("event", "required", "is_active")
    list_editable = ("order", "required", "is_active")
    search_fields = ("prompt", "event__event_name")
    ordering = ("event", "order", "id")


class EventRegistrationAnswerInline(TabularInline):
    """Inline editor for registration answers."""

    model = EventRegistrationAnswer
    extra = 0
    fields = ("order", "question", "question_prompt", "answer_text")
    ordering = ("order", "id")
    show_change_link = False


@admin.register(EventRegistration)
class EventRegistrationAdmin(ModelAdmin):
    """Admin interface for event registrations."""

    inlines = [EventRegistrationAnswerInline]

    list_display = (
        "event",
        "member",
        "status",
        "ticket_label",
        "primary_email_subscribed",
        "secondary_email_subscribed",
        "phone_subscribed",
        "phone_verified",
        "submitted_at",
        "updated_at",
    )
    list_filter = ("event", "status", "phone_subscribed", "phone_verified")
    search_fields = (
        "member__username",
        "member__email",
        "member__first_name",
        "member__last_name",
        "source_email",
        "registration_token",
        "ticket_label",
    )
    readonly_fields = ("registration_token", "otp_requested_at", "otp_verified_at", "submitted_at", "registered_at")
    autocomplete_fields = ("event", "member", "ticket_option")
    ordering = ("-registered_at",)


@admin.register(EventRegistrationAnswer)
class EventRegistrationAnswerAdmin(ModelAdmin):
    """Admin interface for registration answers."""

    list_display = ("registration", "order", "question_prompt", "updated_at")
    list_filter = ("registration__event",)
    search_fields = ("question_prompt", "answer_text", "registration__member__username", "registration__member__email")
    ordering = ("registration", "order", "id")
