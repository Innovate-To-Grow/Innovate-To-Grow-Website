from django.conf import settings
from django.db import models

from apps.core.models import ProjectControlModel


class CustomCssRevision(ProjectControlModel):
    """A saved version of the Site Settings custom CSS, kept so an admin can restore it."""

    site_settings = models.ForeignKey(
        "cms.SiteSettings",
        on_delete=models.CASCADE,
        related_name="custom_css_revisions",
    )
    css = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Custom CSS revision"
        verbose_name_plural = "Custom CSS revisions"

    def __str__(self):
        return f"Custom CSS of {self.created_at:%Y-%m-%d %H:%M}"
