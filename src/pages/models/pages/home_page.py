"""
Home page model for the main landing page.

Supports multiple versions with only one active at a time.
Content is composed of ordered PageComponent blocks.
"""

from django.db import models

from core.models.base import ProjectControlModel


class HomePage(ProjectControlModel):
    """Home page model composed of ordered PageComponents (one version active)."""

    name = models.CharField(max_length=200, help_text="Internal name to identify this home page version")
    is_active = models.BooleanField(default=False, help_text="Only one home page can be active at a time")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Home Page"
        verbose_name_plural = "Home Pages"

    def save(self, *args, **kwargs):
        # If this home page is being set as active, deactivate all others
        if self.is_active:
            HomePage.objects.exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

    def __str__(self):
        status = " (Active)" if self.is_active else ""
        return f"{self.name}{status}"

    @classmethod
    def get_active(cls):
        """Get the currently active home page."""
        return cls.objects.filter(is_active=True).first()

    @property
    def ordered_components(self):
        """Return enabled components ordered for rendering."""
        return self.components.filter(is_enabled=True).order_by("order", "id")

    @property
    def all_components(self):
        """Return all components (including disabled) ordered."""
        return self.components.order_by("order", "id")
