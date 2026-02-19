"""Presentation model for event hierarchy."""

from django.core.validators import MinValueValidator
from django.db import models


class Presentation(models.Model):
    """Individual presentation within a track."""

    track = models.ForeignKey(
        "events.Track",
        on_delete=models.CASCADE,
        related_name="presentations",
        help_text="The track this presentation belongs to.",
    )
    order = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text="Presentation order within the track (must be > 0).",
    )
    team_id = models.CharField(max_length=255, blank=True, null=True, help_text="Team identifier.")
    team_name = models.CharField(max_length=255, blank=True, null=True, help_text="Name of the team.")
    project_title = models.CharField(max_length=500, help_text="Title of the project.")
    organization = models.CharField(max_length=255, blank=True, null=True, help_text="Organization name.")
    abstract = models.TextField(blank=True, null=True, help_text="Abstract/project description.")

    def __str__(self):
        team_display = self.team_name if self.team_name else "Break"
        return f"{self.track.track_name} #{self.order}: {team_display} - {self.project_title}"

    class Meta:
        ordering = ["order", "id"]
        unique_together = [["track", "order"]]
        verbose_name = "Presentation"
        verbose_name_plural = "Presentations"
