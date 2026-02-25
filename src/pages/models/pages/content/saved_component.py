"""
SavedComponent model for the reusable component library.

Allows editors to save GrapesJS components and reuse them across pages.
"""

import uuid

from django.conf import settings
from django.db import models


class SavedComponent(models.Model):
    """A reusable GrapesJS component saved by an editor."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, help_text="User-defined component name.")
    category = models.CharField(max_length=100, default="Custom", help_text="Component category for grouping.")
    grapesjs_data = models.JSONField(default=dict, help_text="GrapesJS component JSON data.")
    html = models.TextField(blank=True, default="", help_text="Rendered HTML for preview.")
    css = models.TextField(blank=True, default="", help_text="Associated CSS styles.")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="saved_components",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    is_shared = models.BooleanField(default=True, help_text="Visible to all editors or just the creator.")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Saved Component"
        verbose_name_plural = "Saved Components"

    def __str__(self):
        return f"{self.name} ({self.category})"
