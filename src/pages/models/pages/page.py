"""
Page model for content management.

Supports:
- Rich text pages (images, tables, formatting, embedded YouTube links via CKEditor).
- External URL redirect pages.
"""

import uuid

from django.db import models
from ckeditor_uploader.fields import RichTextUploadingField
from .mixins import AnalyticsFieldsMixin, PublishingFieldsMixin, SEOFieldsMixin
from .validators import validate_nested_slug


# ============================== Page Model ==============================

class Page(SEOFieldsMixin, AnalyticsFieldsMixin, PublishingFieldsMixin, models.Model):
    """
    Content page model.

    Supports:
    - Rich text (images, tables, formatting, embedded YouTube links via CKEditor).
    - External URL redirect pages.
    """

    # Technical identifier (not primary key, just an extra UUID)
    page_uuid = models.UUIDField(default=uuid.uuid4, editable=False)

    # Page type choices
    PAGE_TYPE_CHOICES = [
        ('page', 'Rich Text Page'),
        ('external', 'External URL'),
    ]

    # ------------------------------ Basic Fields ------------------------------

    title = models.CharField(
        max_length=200,
        help_text="Human readable title of the page."
    )
    slug = models.CharField(
        max_length=255,
        unique=True,
        validators=[validate_nested_slug],
        help_text=(
            "User-defined slug. Supports nested paths, e.g. 'about/team'. "
            "Do NOT include leading or trailing '/'."
        ),
    )
    page_type = models.CharField(
        max_length=20,
        choices=PAGE_TYPE_CHOICES,
        default='page',
        help_text="Page behavior type."
    )

    # Rich text page body (CKEditor with upload, can embed images / videos / code)
    page_body = RichTextUploadingField(
        blank=True,
        null=True,
        help_text="Rich text content for 'page' type."
    )

    # External URL page fields
    external_url = models.URLField(
        blank=True,
        null=True,
        help_text="Target URL for 'external' type page."
    )

    # -------------------------- Utility Methods ----------------------------

    def save(self, *args, **kwargs):
        """
        Override save to automatically maintain some redundant fields.
        """
        # Keep slug_depth updated from slug (number of '/' characters)
        self.slug_depth = self.slug.count('/')

        # Ensure meta_title has a default value
        if not self.meta_title:
            self.meta_title = self.title[:255]

        super().save(*args, **kwargs)

    def get_absolute_url(self):
        """
        Return the absolute URL path for this page.
        Returns a frontend-friendly path for Vue Router.
        """
        return f'/pages/{self.slug}'

    @property
    def page_type_label(self) -> str:
        """
        Human readable page type label, using Django's built-in display helper.
        """
        return self.get_page_type_display()

    @property
    def effective_meta_title(self) -> str:
        """
        Return the final meta title used for SEO (meta_title or fallback to title).
        """
        return self.meta_title or self.title

    def __str__(self) -> str:
        return f"{self.slug} - {self.title}"

    class Meta:
        ordering = ['slug']
        verbose_name = "Page"
        verbose_name_plural = "Pages"
