from django.db import models

from core.models import ProjectControlModel


class RegistrationSheetSyncLog(ProjectControlModel):
    class SyncType(models.TextChoices):
        APPEND = "append", "Append Row"
        FULL = "full", "Full Sync"

    class Status(models.TextChoices):
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    event = models.ForeignKey(
        "event.Event",
        on_delete=models.CASCADE,
        related_name="sheet_sync_logs",
    )
    sync_type = models.CharField(max_length=10, choices=SyncType.choices)
    status = models.CharField(max_length=10, choices=Status.choices)
    rows_written = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["event", "created_at"]),
        ]

    def __str__(self):
        return f"{self.event.name} — {self.get_sync_type_display()} — {self.get_status_display()}"
