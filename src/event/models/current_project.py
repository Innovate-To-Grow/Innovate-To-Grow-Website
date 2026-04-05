from django.db import models

from core.models import ProjectControlModel


class CurrentProjectSchedule(ProjectControlModel):
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
    last_synced_at = models.DateTimeField(null=True, blank=True, editable=False)
    sync_error = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = "Current Project and Schedule"
        verbose_name_plural = "Current Project and Schedule"

    def __str__(self):
        if self.sheet_id:
            return f"Sheet: {self.sheet_id[:20]}..."
        return "Not configured"

    @classmethod
    def load(cls):
        return cls.objects.first() or cls()
