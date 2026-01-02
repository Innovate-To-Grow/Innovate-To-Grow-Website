from django.db import models

from core.models.base import TimeStampedModel


class SEOFieldsMixin(TimeStampedModel):
    """Reusable SEO and Open Graph fields."""

    meta_title = models.CharField(
        max_length=255,
        blank=True,
        help_text="SEO title (will fall back to page title if empty)."
    )
    meta_description = models.TextField(
        blank=True,
        help_text="SEO description for search engines and social sharing."
    )
    meta_keywords = models.CharField(
        max_length=255,
        blank=True,
        help_text="Comma-separated SEO keywords (optional, some search engines may ignore this)."
    )
    og_image = models.URLField(
        blank=True,
        null=True,
        help_text="Open Graph share image URL (e.g. for social media cards)."
    )
    canonical_url = models.URLField(
        blank=True,
        null=True,
        help_text="Canonical URL for SEO (optional, usually auto-resolved)."
    )
    meta_robots = models.CharField(
        max_length=100,
        blank=True,
        help_text="Robots meta tag value, e.g. 'index,follow' or 'noindex,nofollow'."
    )
    google_site_verification = models.CharField(
        max_length=255,
        blank=True,
        help_text="Google Search Console verification token for this page (optional)."
    )
    google_structured_data = models.JSONField(
        blank=True,
        null=True,
        help_text="Optional JSON-LD structured data payload for Google Search."
    )

    class Meta:
        abstract = True


class AnalyticsFieldsMixin(TimeStampedModel):
    """Reusable analytics and rendering metadata."""

    slug_depth = models.PositiveIntegerField(
        default=0,
        help_text="Redundant: number of path segments (e.g. 'about/team' -> 1 slash)."
    )
    view_count = models.PositiveIntegerField(
        default=0,
        help_text="Redundant: total view count (may be updated externally)."
    )
    last_viewed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Redundant: timestamp of last page view."
    )
    template_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional template name override for rendering this page."
    )

    class Meta:
        abstract = True


class PublishingFieldsMixin(TimeStampedModel):
    """Common publishing flags and timestamps."""

    published = models.BooleanField(
        default=False,
        help_text="Whether this page is visible to the public."
    )

    class Meta:
        abstract = True
