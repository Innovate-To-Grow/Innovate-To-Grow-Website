"""Program model for event hierarchy."""

from django.core.validators import MinValueValidator
from django.db import models


class Program(models.Model):
    """Top-level program grouping within an event."""

    event = models.ForeignKey(
        "events.Event",
        on_delete=models.CASCADE,
        related_name="programs",
        help_text="The event this program belongs to.",
    )
    program_name = models.CharField(max_length=255, help_text="Name of the program.")
    order = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Display order for programs.",
    )

    def __str__(self):
        return f"{self.event.event_name} - {self.program_name}"

    class Meta:
        ordering = ["order", "id"]
        unique_together = [["event", "program_name"]]
        verbose_name = "Program"
        verbose_name_plural = "Programs"
