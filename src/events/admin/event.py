"""
Admin interface for Event model with inline editors.
"""

from django.contrib import admin
from unfold.admin import ModelAdmin, StackedInline, TabularInline

from ..models import (
    Event,
    EventQuestion,
    EventTicketOption,
    Program,
    SpecialAward,
    TrackWinner,
)


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
                "fields": (
                    "upper_bullet_points",
                    "lower_bullet_points",
                    "expo_table",
                    "reception_table",
                    "special_awards",
                ),
            },
        ),
        (
            "Publishing",
            {
                "fields": ("is_published", "is_live", "created_at", "updated_at"),
            },
        ),
    )
