"""
Page model for content management.

Stores display content via ordered PageComponent blocks instead of a single
body field or external URL flag.
"""

import uuid

from django.db import models

from core.models.base import AuthoredModel, SoftDeleteModel, TimeStampedModel

from .mixins import AnalyticsFieldsMixin, PublishingFieldsMixin, SEOFieldsMixin
from .validators import validate_nested_slug

# ============================== Page Model ==============================


class Page(
    SEOFieldsMixin, AnalyticsFieldsMixin, PublishingFieldsMixin, SoftDeleteModel, AuthoredModel, TimeStampedModel
):
    """Content page model composed of ordered PageComponents."""

    # Technical identifier (not primary key, just an extra UUID)
    page_uuid = models.UUIDField(default=uuid.uuid4, editable=False)

    # ------------------------------ Basic Fields ------------------------------

    title = models.CharField(max_length=200, help_text="Human readable title of the page.")
    slug = models.CharField(
        max_length=255,
        unique=True,
        validators=[validate_nested_slug],
        help_text=(
            "User-defined slug. Supports nested paths, e.g. 'about/team'. Do NOT include leading or trailing '/'."
        ),
    )
    # -------------------------- Utility Methods ----------------------------

    def save(self, *args, **kwargs):
        """
        Override save to automatically maintain some redundant fields.
        """
        # Keep slug_depth updated from slug (number of '/' characters)
        self.slug_depth = self.slug.count("/")

        # Ensure meta_title has a default value
        if not self.meta_title:
            self.meta_title = self.title[:255]

        super().save(*args, **kwargs)

    def get_absolute_url(self):
        """
        Return the absolute URL path for this page.
        Returns a frontend-friendly path for Vue Router.
        """
        return f"/pages/{self.slug}"

    @property
    def ordered_components(self):
        """Return components ordered for rendering."""
        return self.components.order_by("order", "id")

    @property
    def effective_meta_title(self) -> str:
        """
        Return the final meta title used for SEO (meta_title or fallback to title).
        """
        return self.meta_title or self.title

    def __str__(self) -> str:
        return f"{self.slug} - {self.title}"

    class Meta:
        ordering = ["slug"]
        verbose_name = "Page"
        verbose_name_plural = "Pages"
