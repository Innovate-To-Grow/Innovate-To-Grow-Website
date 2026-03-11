from django.db import models

from core.models import ProjectControlModel


class Question(ProjectControlModel):
    event = models.ForeignKey("event.Event", on_delete=models.CASCADE, related_name="questions")
    text = models.CharField(max_length=500)
    is_required = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"{self.event.name} - {self.text[:50]}"
