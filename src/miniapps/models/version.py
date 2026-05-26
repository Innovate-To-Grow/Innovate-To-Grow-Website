from django.conf import settings
from django.db import models

from core.models import ProjectControlModel


class MiniAppVersion(ProjectControlModel):
    """Immutable snapshot of a mini-app's code at publish time."""

    app = models.ForeignKey("miniapps.MiniApp", on_delete=models.CASCADE, related_name="versions")
    version_number = models.PositiveIntegerField()
    html_code = models.TextField(blank=True, default="")
    js_code = models.TextField(blank=True, default="")
    css_code = models.TextField(blank=True, default="")
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="miniapp_versions",
    )

    class Meta:
        unique_together = [("app", "version_number")]
        ordering = ["-version_number"]
        verbose_name = "App Version"
        verbose_name_plural = "App Versions"

    def __str__(self):
        return f"{self.app.title} v{self.version_number}"
