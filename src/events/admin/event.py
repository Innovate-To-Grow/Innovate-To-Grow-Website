"""
Admin interface for Event models with inline editors.
"""

from django.contrib import admin
from unfold.admin import ModelAdmin, StackedInline, TabularInline

from ..models import (
    Event,
    EventQuestion,
    EventRegistration,
    EventRegistrationAnswer,
    EventTicketOption,
    Presentation,
    Program,
    SpecialAward,
    Track,
    TrackWinner,
)


class PresentationInline(TabularInline):
    """Inline editor for Presentations within a Track."""

    model = Presentation
    extra = 0
    fields = ("order", "team_id", "team_name", "project_title", "organization")
    ordering = ("order", "id")


class TrackInline(TabularInline):
    """Inline editor for Tracks within a Program."""

    model = Track
    extra = 0
    fields = ("track_name", "room", "order")
    ordering = ("order", "id")
    show_change_link = True


class ProgramInline(StackedInline):
    """Inline editor for Programs within an Event."""

    model = Program
    extra = 0
    fields = ("program_name", "order")
    ordering = ("order", "id")
    show_change_link = True


class TrackWinnerInline(TabularInline):
    """Inline editor for Track Winners within an Event."""

    model = TrackWinner
    fk_name = "event"
    extra = 0
    fields = ("track_name", "winner_name")


class SpecialAwardInline(TabularInline):
    """Inline editor for Special Awards within an Event."""

    model = SpecialAward
    fk_name = "event"
    extra = 0
    fields = ("program_name", "award_winner")


class EventTicketOptionInline(TabularInline):
    """Inline editor for event ticket options."""

    model = EventTicketOption
    extra = 0
    fields = ("label", "order", "is_active")
    ordering = ("order", "id")


class EventQuestionInline(TabularInline):
    """Inline editor for event registration questions."""

    model = EventQuestion
    extra = 0
    fields = ("prompt", "order", "required", "is_active")
    ordering = ("order", "id")


@admin.register(Event)
class EventAdmin(ModelAdmin):
    """Admin interface for Event model with hierarchical inlines."""

    inlines = [
        ProgramInline,
        TrackWinnerInline,
        SpecialAwardInline,
        EventTicketOptionInline,
        EventQuestionInline,
    ]

    list_display = ("event_name", "event_date_time", "is_published", "is_live", "updated_at")
    list_filter = ("is_published", "is_live", "event_date_time", "created_at")
    search_fields = ("event_name", "slug")
    readonly_fields = ("event_uuid", "created_at", "updated_at")
    prepopulated_fields = {"slug": ("event_name",)}

    fieldsets = (
        ("Basic Information", {"fields": ("event_uuid", "event_name", "slug", "event_date_time")}),
        (
            "Content",
            {
                "fields": ("upper_bullet_points", "lower_bullet_points", "expo_table", "reception_table", "special_awards"),
            },
        ),
        (
            "Publishing",
            {
                "fields": ("is_published", "is_live", "created_at", "updated_at"),
            },
        ),
    )


@admin.register(Track)
class TrackAdmin(ModelAdmin):
    """Admin interface for Track model with Presentation inlines."""

    inlines = [PresentationInline]

    list_display = ("track_name", "program", "room", "start_time", "order")
    list_display_links = ("track_name",)
    list_editable = ("order",)
    list_filter = ("program__event", "program")
    search_fields = ("track_name", "room", "program__program_name")
    ordering = ("program__order", "order", "id")


@admin.register(Program)
class ProgramAdmin(ModelAdmin):
    """Admin interface for Program model with Track inlines."""

    inlines = [TrackInline]

    list_display = ("program_name", "event", "order")
    list_display_links = ("program_name",)
    list_editable = ("order",)
    list_filter = ("event",)
    search_fields = ("program_name", "event__event_name")
    ordering = ("event", "order", "id")


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
