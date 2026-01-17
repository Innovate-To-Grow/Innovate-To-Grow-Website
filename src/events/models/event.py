"""
Event models for hierarchical event structure.

Event -> Program -> Track -> Presentation
"""

import uuid

from django.core.validators import MinValueValidator
from django.db import models

from core.models import OrderedModel, ProjectControlModel


class Event(ProjectControlModel):
    """Core event model containing basic info and markdown bullet points."""

    event_uuid = models.UUIDField(
        default=uuid.uuid4, editable=False, unique=True, help_text="Unique identifier for the event."
    )

    # Basic Info
    event_name = models.CharField(max_length=255, help_text="Name of the event.")
    event_date = models.DateField(help_text="Date of the event.")
    event_time = models.TimeField(help_text="Time of the event.")

    # Markdown bullet points (stored as JSON arrays)
    upper_bullet_points = models.JSONField(
        default=list, blank=True, help_text="Upper bullet points in Markdown format (array of strings)."
    )
    lower_bullet_points = models.JSONField(
        default=list, blank=True, help_text="Lower bullet points in Markdown format (array of strings)."
    )

    # Expo and Reception tables (stored as JSON arrays)
    expo_table = models.JSONField(default=list, blank=True, help_text="Expo table rows: [{time, room, description}]")
    reception_table = models.JSONField(
        default=list, blank=True, help_text="Reception table rows: [{time, room, description}]"
    )

    # Publishing
    is_published = models.BooleanField(default=False, help_text="Whether this event is published and visible.")

    def __str__(self):
        return f"{self.event_name} ({self.event_date})"

    class Meta:
        ordering = ["-event_date", "-created_at"]
        verbose_name = "Event"
        verbose_name_plural = "Events"


class Program(OrderedModel):
    """Top-level program grouping within an event."""

    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name="programs", help_text="The event this program belongs to."
    )
    program_name = models.CharField(max_length=255, help_text="Name of the program.")

    def __str__(self):
        return f"{self.event.event_name} - {self.program_name}"

    class Meta:
        ordering = ["order", "id"]
        unique_together = [["event", "program_name"]]
        verbose_name = "Program"
        verbose_name_plural = "Programs"


class Track(OrderedModel):
    """Track within a program, assigned to a room."""

    program = models.ForeignKey(
        Program, on_delete=models.CASCADE, related_name="tracks", help_text="The program this track belongs to."
    )
    track_name = models.CharField(max_length=255, help_text="Name of the track.")
    room = models.CharField(max_length=255, help_text="Room assignment for this track.")
    start_time = models.TimeField(null=True, blank=True, help_text="Start time for presentations in this track.")

    def __str__(self):
        return f"{self.program.program_name} - {self.track_name} ({self.room})"

    class Meta:
        ordering = ["order", "id"]
        unique_together = [["program", "track_name"]]
        verbose_name = "Track"
        verbose_name_plural = "Tracks"


class Presentation(models.Model):
    """Individual presentation within a track."""

    track = models.ForeignKey(
        Track,
        on_delete=models.CASCADE,
        related_name="presentations",
        help_text="The track this presentation belongs to.",
    )
    order = models.PositiveIntegerField(
        validators=[MinValueValidator(1)], help_text="Presentation order within the track (must be > 0)."
    )
    team_id = models.CharField(max_length=255, blank=True, null=True, help_text="Team identifier.")
    team_name = models.CharField(max_length=255, blank=True, null=True, help_text="Name of the team.")
    project_title = models.CharField(max_length=500, help_text="Title of the project.")
    organization = models.CharField(max_length=255, blank=True, null=True, help_text="Organization name.")

    def __str__(self):
        team_display = self.team_name if self.team_name else "Break"
        return f"{self.track.track_name} #{self.order}: {team_display} - {self.project_title}"

    class Meta:
        ordering = ["order", "id"]
        unique_together = [["track", "order"]]
        verbose_name = "Presentation"
        verbose_name_plural = "Presentations"
