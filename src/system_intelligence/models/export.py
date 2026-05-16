from django.conf import settings
from django.db import models

from core.models.base.control import ProjectControlModel

from .chat import ChatConversation


def _export_upload_to(instance, filename):
    return f"system_intelligence_exports/{instance.id}/{filename}"


class SystemIntelligenceExport(ProjectControlModel):
    """A downloadable file (Excel) the AI generated on behalf of an admin.

    Created by ``export_*_to_excel`` tools. The ``file`` lives under
    MEDIA_ROOT and is served via the dedicated download view, which authorizes
    against ``created_by`` so admins only see their own exports.
    """

    conversation = models.ForeignKey(
        ChatConversation,
        on_delete=models.CASCADE,
        related_name="exports",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="system_intelligence_exports",
    )
    title = models.CharField(max_length=200, default="Export")
    filename = models.CharField(max_length=200)
    file = models.FileField(upload_to=_export_upload_to)
    model_label = models.CharField(max_length=100, blank=True, default="")
    field_names = models.JSONField(default=list, blank=True)
    row_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "System Intelligence Export"

    def __str__(self):
        return f"{self.title} ({self.row_count} rows)"
