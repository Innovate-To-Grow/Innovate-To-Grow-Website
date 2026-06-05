from django.db import models

from apps.core.models import ProjectControlModel


class PastProjectShare(ProjectControlModel):
    rows = models.JSONField(default=list)
    note = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        "authn.Member",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="past_project_shares",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Past Project Share {self.pk}"
