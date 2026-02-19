from django.db import models

from core.models import ProjectControlModel


class GoogleSheet(ProjectControlModel):
    """Saved Google Sheet configuration for rendering component tables."""

    name = models.CharField(
        max_length=255,
        unique=True,
        help_text="Internal display name used by admins to select this Google Sheet.",
    )
    spreadsheet_id = models.CharField(
        max_length=255,
        help_text="Google Spreadsheet ID from the sheet URL.",
    )
    sheet_name = models.CharField(
        max_length=255,
        help_text="Worksheet/tab name inside the spreadsheet.",
    )
    range_a1 = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Optional A1 range override, for example A1:Z100.",
    )
    cache_ttl_seconds = models.PositiveIntegerField(
        default=300,
        help_text="How long fetched sheet data should be cached in seconds.",
    )
    is_enabled = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Disable to block public API access to this saved sheet.",
    )

    class Meta:
        verbose_name = "Google Sheet"
        verbose_name_plural = "Google Sheets"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["spreadsheet_id", "sheet_name"]),
        ]

    def __str__(self) -> str:
        return self.name
