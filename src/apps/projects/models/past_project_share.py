from django.db import models

from core.models import ProjectControlModel


class PastProjectShare(ProjectControlModel):
    rows = models.JSONField(default=list)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Past Project Share {self.pk}"
