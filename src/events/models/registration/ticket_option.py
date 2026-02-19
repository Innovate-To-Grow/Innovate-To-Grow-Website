"""Event ticket option model."""

from django.db import models

from core.models.base.control import ProjectControlModel


class EventTicketOption(ProjectControlModel):
    """Ticket options configured per event (e.g. Attendee, Judge)."""

    event = models.ForeignKey(
        "events.Event",
        on_delete=models.CASCADE,
        related_name="ticket_options",
    )
    label = models.CharField(max_length=255)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "created_at", "id"]
        unique_together = [["event", "label"]]
        indexes = [
            models.Index(fields=["event", "order"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return f"{self.event.event_name} - {self.label}"
