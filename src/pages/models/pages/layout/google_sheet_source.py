from django.db import models

from core.models import ProjectControlModel


class GoogleSheetSource(ProjectControlModel):
    """Configuration for a Google Sheets data source served via the backend API."""

    SHEET_TYPE_CHOICES = [
        ("current-event", "Current Event"),
        ("past-projects", "Past Projects"),
        ("archive-event", "Archive Event"),
    ]

    slug = models.SlugField(unique=True, help_text="API lookup key, e.g. 'current-event', '2025-fall'")
    title = models.CharField(max_length=200, help_text="Display name")
    sheet_type = models.CharField(max_length=20, choices=SHEET_TYPE_CHOICES, help_text="Controls parsing logic")

    spreadsheet_id = models.CharField(max_length=200, help_text="Google Sheets spreadsheet ID")
    range_a1 = models.CharField(max_length=200, help_text="Sheet range, e.g. 'A1:Y76' or 'Past-Projects-WEB-LIVE'")

    tracks_spreadsheet_id = models.CharField(
        max_length=200, blank=True, default="", help_text="Optional separate spreadsheet for track info"
    )
    tracks_sheet_name = models.CharField(
        max_length=200, blank=True, default="", help_text="Track info sheet name, e.g. '2025-I2G2-Tracks'"
    )

    semester_filter = models.CharField(
        max_length=100, blank=True, default="", help_text="Optional row filter, e.g. '2025-2 Fall'"
    )

    cache_ttl_seconds = models.PositiveIntegerField(default=300, help_text="Cache TTL in seconds")
    is_active = models.BooleanField(default=True, help_text="Disable without deleting")

    class Meta:
        ordering = ["slug"]
        verbose_name = "Sheet Source"
        verbose_name_plural = "Sheet Sources"

    def __str__(self):
        return f"{self.title} ({self.slug})"
