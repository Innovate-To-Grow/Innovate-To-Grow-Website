import uuid

from django.conf import settings
from django.db import models


class PageView(models.Model):
    """Tracks individual page visits across the site.

    This is a high-volume write model that intentionally does NOT extend
    ProjectControlModel — soft delete and version tracking add unnecessary
    overhead for ephemeral analytics data.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    path = models.CharField(max_length=2048, db_index=True)
    referrer = models.URLField(max_length=2048, blank=True, default="")
    # No column limit; the write path cuts it to 512 characters (apps.cms.services.analytics.record).
    user_agent = models.TextField(blank=True, default="")
    ip_address = models.GenericIPAddressField(null=True, blank=True, db_index=True)
    # Random id the browser keeps in localStorage and sends with every page view. Campus visitors share one public
    # IP, so this, not ip_address, is what tells visitors apart (ip_address stays for audit and geolocation). NULL on
    # rows recorded before the frontend sent it and for clients that still do not; the admin stats then fall back
    # to ip_address through COALESCE, which is why this string column is nullable rather than "". Not indexed:
    # no query filters on it (COALESCE is an expression, admin search is icontains), and this is the largest
    # write-heavy table.
    visitor_id = models.CharField(max_length=64, null=True, blank=True)
    member = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="page_views",
    )
    session_key = models.CharField(max_length=64, blank=True, default="", db_index=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "analytics_pageview"
        ordering = ["-timestamp"]
        verbose_name = "Page View"
        verbose_name_plural = "Page Views"
        indexes = [
            models.Index(fields=["path", "timestamp"], name="analytics_p_path_51c7b7_idx"),
        ]

    def __str__(self):
        return f"{self.path} @ {self.timestamp}"
