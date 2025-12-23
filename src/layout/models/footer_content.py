from django.core.cache import cache
from django.db import models


def default_footer_content():
    """
    Default empty content structure for footer JSON.

    Stored as JSON so the layout can be managed without code changes.
    """
    return {
        "cta_buttons": [],
        "contact_html": "",
        "columns": [],
        "social_links": [],
        "copyright": "",
        "footer_links": [],
    }


FOOTER_CACHE_KEY = "layout.footer_content.active"
FOOTER_CACHE_TIMEOUT = 300  # seconds


class FooterContent(models.Model):
    """
    Stores the entire footer layout as JSON so it can be edited in admin.

    Only one FooterContent should be active at a time; saving an active record
    will automatically deactivate the others.
    """

    name = models.CharField(
        max_length=200,
        help_text="Internal name to identify this footer version",
    )
    slug = models.SlugField(
        max_length=100,
        unique=True,
        help_text="Machine-readable key for this footer version",
    )
    content = models.JSONField(
        default=default_footer_content,
        help_text="Structured JSON describing footer sections, links, and CTAs",
    )
    is_active = models.BooleanField(
        default=False,
        help_text="Only one footer can be active at a time",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "pages_footercontent"
        ordering = ["-created_at"]
        verbose_name = "Footer Content"
        verbose_name_plural = "Footer Contents"

    def __str__(self):
        status = " (Active)" if self.is_active else ""
        return f"{self.name}{status}"

    def save(self, *args, **kwargs):
        # Ensure only one active footer at a time
        if self.is_active:
            FooterContent.objects.exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)
        # Invalidate cache so future reads pick up the latest active footer
        cache.delete(FOOTER_CACHE_KEY)

    @classmethod
    def get_active(cls):
        """
        Return the currently active footer content.

        Cached for a short period to avoid hitting the database on every request.
        """
        cached = cache.get(FOOTER_CACHE_KEY)
        if cached is not None:
            return cached

        footer = cls.objects.filter(is_active=True).first()
        cache.set(FOOTER_CACHE_KEY, footer, FOOTER_CACHE_TIMEOUT)
        return footer

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        cache.delete(FOOTER_CACHE_KEY)
