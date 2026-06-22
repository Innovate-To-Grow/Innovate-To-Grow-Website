from django.db import models

from apps.core.models import ProjectControlModel


class PastProjectShare(ProjectControlModel):
    name = models.CharField(max_length=200, default="")
    rows = models.JSONField(default=list)
    note = models.TextField(blank=True, default="")
    details_text = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        "authn.Member",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="past_project_shares",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Project Resource Share"
        verbose_name_plural = "Project Resource Shares"

    def __str__(self):
        return self.name or f"Project Resource Share {self.pk}"
