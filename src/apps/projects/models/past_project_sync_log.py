from django.db import models

from apps.core.models import ProjectControlModel


class PastProjectSyncLog(ProjectControlModel):
    class SyncType(models.TextChoices):
        MANUAL = "manual", "Manual Pull"
        AUTO = "auto", "Auto Sync"

    class Status(models.TextChoices):
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    config = models.ForeignKey(
        "projects.PastProjectsSheetConfig",
        on_delete=models.CASCADE,
        related_name="sync_logs",
    )
    sync_type = models.CharField(max_length=10, choices=SyncType.choices)
    status = models.CharField(max_length=10, choices=Status.choices)
    rows_read = models.PositiveIntegerField(default=0)
    projects_created = models.PositiveIntegerField(default=0)
    projects_updated = models.PositiveIntegerField(default=0)
    projects_deleted = models.PositiveIntegerField(default=0)
    semesters_touched = models.PositiveIntegerField(default=0)
    rows_skipped = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Project Resource Sync Log"
        verbose_name_plural = "Project Resource Sync Logs"

    def __str__(self):
        return f"{self.config} — {self.get_sync_type_display()} — {self.get_status_display()}"
