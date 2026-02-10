"""
Page model for content management.

Stores display content via ordered PageComponent blocks instead of a single
body field or external URL flag.
"""

import uuid

from django.core.cache import cache
from django.db import models

from core.models import AuthoredModel, ProjectControlModel

from .mixins import AnalyticsFieldsMixin, SEOFieldsMixin, WorkflowPublishingMixin
from .validators import validate_nested_slug

# ============================== Cache Configuration ==============================

PAGE_CACHE_KEY_PREFIX = "pages.page"
PAGE_CACHE_TIMEOUT = 300  # 5 minutes

# ============================== Page Model ==============================


class Page(SEOFieldsMixin, AnalyticsFieldsMixin, WorkflowPublishingMixin, AuthoredModel, ProjectControlModel):
    """Content page model composed of ordered PageComponents."""

    # Technical identifier
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

    class Meta:
        ordering = ["slug"]
        verbose_name = "Page"
        verbose_name_plural = "Pages"

    # -------------------------- Utility Methods ----------------------------

    def save(self, *args, **kwargs):
        """
        Override save to automatically maintain some redundant fields
        and invalidate cache.
        """
        # Keep slug_depth updated from slug (number of '/' characters)
        self.slug_depth = self.slug.count("/")

        # Ensure meta_title has a default value
        if not self.meta_title:
            self.meta_title = self.title[:255]

        super().save(*args, **kwargs)

        # Invalidate cache
        cache.delete(f"{PAGE_CACHE_KEY_PREFIX}.slug.{self.slug}")
        cache.delete(f"{PAGE_CACHE_KEY_PREFIX}.list")

    def delete(self, *args, **kwargs):
        """Override delete to invalidate cache."""
        slug = self.slug
        super().delete(*args, **kwargs)
        cache.delete(f"{PAGE_CACHE_KEY_PREFIX}.slug.{slug}")
        cache.delete(f"{PAGE_CACHE_KEY_PREFIX}.list")

    def get_absolute_url(self):
        """
        Return the absolute URL path for this page.
        Returns a frontend-friendly path for the React Router.
        """
        return f"/pages/{self.slug}"

    @classmethod
    def get_published_by_slug(cls, slug):
        """
        Retrieve a published page by slug, with caching.

        Returns the Page instance if found and published, otherwise None.
        """
        cache_key = f"{PAGE_CACHE_KEY_PREFIX}.slug.{slug}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        page = cls.objects.filter(slug=slug, status="published").first()
        if page:
            cache.set(cache_key, page, PAGE_CACHE_TIMEOUT)
        return page

    @property
    def ordered_components(self):
        """Return enabled components ordered for rendering."""
        return self.components.filter(is_enabled=True).order_by("order", "id")

    @property
    def all_components(self):
        """Return all components (including disabled) ordered."""
        return self.components.order_by("order", "id")

    @property
    def effective_meta_title(self) -> str:
        """
        Return the final meta title used for SEO (meta_title or fallback to title).
        """
        return self.meta_title or self.title

    def __str__(self) -> str:
        return f"{self.slug} - {self.title}"
