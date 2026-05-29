from django.db import models

from core.models import ProjectControlModel
from core.models.mixins import ActiveModel


class CurrentProjectSchedule(ActiveModel, ProjectControlModel):
    name = models.CharField(max_length=255, blank=True, default="", verbose_name="Event Name")
    sheet_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Google Sheet ID",
        help_text="The ID of the Google Sheet containing project and schedule data.",
    )
    tracks_gid = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        verbose_name="Tracks Worksheet GID",
        help_text="The GID of the worksheet containing track definitions.",
    )
    projects_gid = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        verbose_name="Projects Worksheet GID",
        help_text="The GID of the worksheet containing project/slot data.",
    )
    show_winners = models.BooleanField(
        default=False, verbose_name="Show Winners", help_text="Display winner data on the schedule page."
    )
    grand_winners = models.JSONField(
        default=list, blank=True, verbose_name="Grand Winners", help_text="Auto-synced from Google Sheet Award rows."
    )
    last_synced_at = models.DateTimeField(null=True, blank=True, editable=False)
    sync_error = models.TextField(blank=True, default="")
    auto_sync_enabled = models.BooleanField(
        default=False, verbose_name="Auto Sync", help_text="Automatically sync from Google Sheets on a schedule."
    )
    sync_interval_minutes = models.PositiveIntegerField(
        default=60,
        verbose_name="Sync Interval (minutes)",
        help_text="How often to auto-sync, in minutes. Used by the sync_schedule management command.",
    )

    class Meta:
        verbose_name = "Current Project and Schedule"
        verbose_name_plural = "Current Project and Schedule"

    def __str__(self):
        return self.name or "Not configured"

    def save(self, **kwargs):
        if self.is_active:
            CurrentProjectSchedule.objects.filter(is_active=True).exclude(pk=self.pk).update(is_active=False)
        super().save(**kwargs)

    @classmethod
    def load(cls):
        """Return the active config, or None if no active config exists."""
        return cls.objects.filter(is_active=True).first()

    @property
    def sync_is_due(self) -> bool:
        """True when auto-sync is enabled and enough time has elapsed."""
        if not self.auto_sync_enabled:
            return False
        if self.last_synced_at is None:
            return True
        from django.utils import timezone

        elapsed = (timezone.now() - self.last_synced_at).total_seconds()
        return elapsed >= self.sync_interval_minutes * 60


class CurrentProject(ProjectControlModel):
    schedule = models.ForeignKey(
        "event.CurrentProjectSchedule",
        on_delete=models.CASCADE,
        related_name="projects",
    )
    class_code = models.CharField(max_length=20, blank=True, default="", db_index=True)
    team_number = models.CharField(max_length=20, blank=True, default="")
    team_name = models.CharField(max_length=255, blank=True, default="")
    project_title = models.CharField(max_length=500)
    organization = models.CharField(max_length=255, blank=True, default="")
    industry = models.CharField(max_length=100, blank=True, default="", db_index=True)
    abstract = models.TextField(blank=True, default="")
    student_names = models.TextField(blank=True, default="")
    is_presenting = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["class_code", "team_number"]
        unique_together = [["schedule", "team_number", "project_title"]]
        verbose_name = "Current Project"

    def __str__(self):
        if self.team_number:
            return f"Team {self.team_number} - {self.project_title[:60]}"
        return self.project_title[:60]
