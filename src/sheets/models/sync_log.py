from django.conf import settings
from django.db import models

from core.models import ProjectControlModel


class SyncLog(ProjectControlModel):
    """Audit trail for sheet sync operations."""

    class Direction(models.TextChoices):
        PULL = "pull", "Pull (Sheet → DB)"
        PUSH = "push", "Push (DB → Sheet)"

    class Status(models.TextChoices):
        SUCCESS = "success", "Success"
        PARTIAL = "partial", "Partial Success"
        FAILED = "failed", "Failed"

    sheet_link = models.ForeignKey(
        "sheets.SheetLink",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sync_logs",
    )
    direction = models.CharField(max_length=4, choices=Direction.choices)
    status = models.CharField(max_length=7, choices=Status.choices)

    # Stats
    rows_processed = models.PositiveIntegerField(default=0)
    rows_created = models.PositiveIntegerField(default=0)
    rows_updated = models.PositiveIntegerField(default=0)
    rows_skipped = models.PositiveIntegerField(default=0)
    rows_failed = models.PositiveIntegerField(default=0)

    error_details = models.JSONField(
        default=list,
        blank=True,
        help_text='List of {"row": N, "error": "..."} entries',
    )

    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sheet_sync_logs",
    )

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "Sync Log"
        verbose_name_plural = "Sync Logs"
        indexes = [
            models.Index(fields=["direction", "status"]),
            models.Index(fields=["sheet_link", "started_at"]),
        ]

    def __str__(self):
        link_name = self.sheet_link.name if self.sheet_link else "(deleted)"
        return f"{self.get_direction_display()} - {link_name} - {self.get_status_display()}"
