from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

from core.models import ProjectControlModel


class MiniAppDataRecord(ProjectControlModel):
    """Stores a single data record for a mini-app, validated against its schema."""

    app = models.ForeignKey("miniapps.MiniApp", on_delete=models.CASCADE, related_name="records")
    data = models.JSONField(default=dict, encoder=DjangoJSONEncoder)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="miniapp_records",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Data Record"
        verbose_name_plural = "Data Records"

    def __str__(self):
        return f"Record {self.pk} for {self.app.title}"
