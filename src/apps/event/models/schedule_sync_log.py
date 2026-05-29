from django.db import models

from core.models import ProjectControlModel


class ScheduleSyncLog(ProjectControlModel):
    class SyncType(models.TextChoices):
        MANUAL = "manual", "Manual Pull"
        AUTO = "auto", "Auto Sync"

    class Status(models.TextChoices):
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    config = models.ForeignKey(
        "event.CurrentProjectSchedule",
        on_delete=models.CASCADE,
        related_name="sync_logs",
    )
    sync_type = models.CharField(max_length=10, choices=SyncType.choices)
    status = models.CharField(max_length=10, choices=Status.choices)
    sections_created = models.PositiveIntegerField(default=0)
    tracks_created = models.PositiveIntegerField(default=0)
    slots_created = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Schedule Sync Log"
        verbose_name_plural = "Schedule Sync Logs"

    def __str__(self):
        return f"{self.config} — {self.get_sync_type_display()} — {self.get_status_display()}"
