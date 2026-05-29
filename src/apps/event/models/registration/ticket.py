import uuid

from django.db import models

from core.models import ProjectControlModel


def generate_barcode():
    return uuid.uuid4().hex.upper()


class Ticket(ProjectControlModel):
    event = models.ForeignKey("event.Event", on_delete=models.CASCADE, related_name="tickets")
    name = models.CharField(max_length=255)
    barcode = models.CharField(max_length=64, unique=True, default=generate_barcode, editable=False)
    order = models.PositiveIntegerField(default=0)

    BARCODE_FORMAT = "PDF417"

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return f"{self.event.name} - {self.name}"
