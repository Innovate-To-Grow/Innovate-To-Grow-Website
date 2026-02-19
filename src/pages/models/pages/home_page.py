"""
Home page model for the main landing page.

Supports multiple versions with only one active at a time.
Content is composed of ordered PageComponent blocks.
Includes publishing workflow: Draft -> Review -> Published.
"""

from django.core.cache import cache
from django.db import models

from core.models import AuthoredModel, ProjectControlModel

from .mixins import ComponentPageMixin, WorkflowPublishingMixin

# ============================== Cache Configuration ==============================

HOMEPAGE_CACHE_KEY = "pages.homepage.active"
HOMEPAGE_CACHE_TIMEOUT = 300  # 5 minutes

# ============================== HomePage Model ==============================


class HomePage(ComponentPageMixin, WorkflowPublishingMixin, AuthoredModel, ProjectControlModel):
    """Home page model composed of ordered PageComponents (one version active)."""

    name = models.CharField(max_length=200, help_text="Internal name to identify this home page version")
    is_active = models.BooleanField(default=False, help_text="Only one home page can be active at a time")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Home Page"
        verbose_name_plural = "Home Pages"

    def save(self, *args, **kwargs):
        # Only allow setting is_active if status is published
        if self.is_active and self.status != self.PublishStatus.PUBLISHED:
            from django.core.exceptions import ValidationError

            raise ValidationError("Cannot activate a home page that is not published.")
        # If this home page is being set as active, deactivate all others
        if self.is_active:
            HomePage.objects.exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)
        # Invalidate cache
        cache.delete(HOMEPAGE_CACHE_KEY)

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        cache.delete(HOMEPAGE_CACHE_KEY)

    def __str__(self):
        parts = [self.name]
        if self.is_active:
            parts.append("(Active)")
        parts.append(f"[{self.get_status_display()}]")
        return " ".join(parts)

    @classmethod
    def get_active(cls):
        """Get the currently active AND published home page, with caching."""
        cached = cache.get(HOMEPAGE_CACHE_KEY)
        if cached is not None:
            return cached

        home = cls.objects.filter(is_active=True, status="published").first()
        cache.set(HOMEPAGE_CACHE_KEY, home, HOMEPAGE_CACHE_TIMEOUT)
        return home

    def unpublish(self, user=None):
        """Revert to Draft and deactivate."""
        self.is_active = False
        self.status = self.PublishStatus.DRAFT
        self.save(update_fields=["status", "is_active", "updated_at"])
        if hasattr(self, "save_version"):
            self.save_version(comment="Unpublished (reverted to draft)", user=user)
