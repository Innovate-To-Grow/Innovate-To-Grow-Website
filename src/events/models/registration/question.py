"""Event registration question model."""

from django.db import models

from core.models.base.control import ProjectControlModel


class EventQuestion(ProjectControlModel):
    """Custom questions asked during event registration."""

    event = models.ForeignKey(
        "events.Event",
        on_delete=models.CASCADE,
        related_name="questions",
    )
    prompt = models.CharField(max_length=500)
    order = models.PositiveIntegerField(default=0)
    required = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "created_at", "id"]
        unique_together = [["event", "prompt"]]
        indexes = [
            models.Index(fields=["event", "order"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return f"{self.event.event_name} - Q{self.order + 1}: {self.prompt[:60]}"
