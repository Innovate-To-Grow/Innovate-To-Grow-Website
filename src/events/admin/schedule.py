"""
Admin interface for Program and Track models (event schedule).
"""

from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from ..models import Presentation, Program, Track


class TrackInline(TabularInline):
    """Inline editor for Tracks within a Program."""

    model = Track
    extra = 0
    fields = ("track_name", "room", "order")
    ordering = ("order", "id")
    show_change_link = True


class PresentationInline(TabularInline):
    """Inline editor for Presentations within a Track."""

    model = Presentation
    extra = 0
    fields = ("order", "team_id", "team_name", "project_title", "organization")
    ordering = ("order", "id")


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
