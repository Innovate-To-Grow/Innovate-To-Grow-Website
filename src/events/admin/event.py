"""
Admin interface for Event models with inline editors.
"""

from django.contrib import admin
from ..models import Event, Program, Track, Presentation, TrackWinner, EventRegistration


class PresentationInline(admin.TabularInline):
    """Inline editor for Presentations within a Track."""

    model = Presentation
    extra = 0
    fields = ('order', 'team_id', 'team_name', 'project_title', 'organization')
    ordering = ('order', 'id')


class TrackInline(admin.TabularInline):
    """Inline editor for Tracks within a Program."""

    model = Track
    extra = 0
    fields = ('track_name', 'room', 'order')
    ordering = ('order', 'id')
    show_change_link = True


class ProgramInline(admin.StackedInline):
    """Inline editor for Programs within an Event."""

    model = Program
    extra = 0
    fields = ('program_name', 'order')
    ordering = ('order', 'id')
    show_change_link = True


class TrackWinnerInline(admin.TabularInline):
    """Inline editor for Track Winners within an Event."""

    model = TrackWinner
    extra = 0
    fields = ('track_name', 'winner_name')


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    """Admin interface for Event model with hierarchical inlines."""

    inlines = [
        ProgramInline,
        TrackWinnerInline,
    ]

    list_display = ('event_name', 'event_date', 'event_time', 'is_published', 'updated_at')
    list_filter = ('is_published', 'event_date', 'created_at')
    search_fields = ('event_name',)
    readonly_fields = ('event_uuid', 'created_at', 'updated_at')

    fieldsets = (
        ('Basic Information', {
            'fields': ('event_uuid', 'event_name', 'event_date', 'event_time')
        }),
        ('Content', {
            'fields': ('upper_bullet_points', 'lower_bullet_points', 'special_awards'),
        }),
        ('Publishing', {
            'fields': ('is_published', 'created_at', 'updated_at'),
        }),
    )


@admin.register(Track)
class TrackAdmin(admin.ModelAdmin):
    """Admin interface for Track model with Presentation inlines."""

    inlines = [PresentationInline]

    list_display = ('track_name', 'program', 'room', 'order')
    list_filter = ('program__event', 'program')
    search_fields = ('track_name', 'room', 'program__program_name')
    ordering = ('program__order', 'order', 'id')


@admin.register(Program)
class ProgramAdmin(admin.ModelAdmin):
    """Admin interface for Program model with Track inlines."""

    inlines = [TrackInline]

    list_display = ('program_name', 'event', 'order')
    list_filter = ('event',)
    search_fields = ('program_name', 'event__event_name')
    ordering = ('event', 'order', 'id')


@admin.register(EventRegistration)
class EventRegistrationAdmin(admin.ModelAdmin):
    """Admin interface for EventRegistration model."""

    list_display = ('member', 'event', 'registered_at', 'updated_at')
    list_filter = ('event', 'registered_at')
    search_fields = (
        'member__username',
        'member__email',
        'member__first_name',
        'member__last_name',
        'event__event_name',
        'event__slug',
    )
    readonly_fields = ('registered_at', 'updated_at')
    autocomplete_fields = ['member', 'event']
    
    fieldsets = (
        ('Registration', {
            'fields': ('event', 'member', 'registered_at', 'updated_at')
        }),
    )

