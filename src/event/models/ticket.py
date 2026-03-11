from django.db import models

from core.models import ProjectControlModel


class Ticket(ProjectControlModel):
    event = models.ForeignKey("event.Event", on_delete=models.CASCADE, related_name="tickets")
    name = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    quantity = models.PositiveIntegerField(default=0, help_text="0 means unlimited")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return f"{self.event.name} - {self.name}"
