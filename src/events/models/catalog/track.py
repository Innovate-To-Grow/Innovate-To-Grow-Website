"""Track model for event hierarchy."""

from django.core.validators import MinValueValidator
from django.db import models


class Track(models.Model):
    """Track within a program, assigned to a room."""

    program = models.ForeignKey(
        "events.Program",
        on_delete=models.CASCADE,
        related_name="tracks",
        help_text="The program this track belongs to.",
    )
    track_name = models.CharField(max_length=255, help_text="Name of the track.")
    room = models.CharField(max_length=255, help_text="Room assignment for this track.")
    start_time = models.TimeField(
        null=True,
        blank=True,
        help_text="Start time for presentations in this track.",
    )
    order = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Display order for tracks within the program.",
    )

    def __str__(self):
        return f"{self.program.program_name} - {self.track_name} ({self.room})"

    class Meta:
        ordering = ["order", "id"]
        unique_together = [["program", "track_name"]]
        verbose_name = "Track"
        verbose_name_plural = "Tracks"
