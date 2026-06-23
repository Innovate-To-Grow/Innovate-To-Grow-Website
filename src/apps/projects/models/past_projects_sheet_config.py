from django.db import models, transaction

from apps.core.models import ProjectControlModel
from apps.core.models.mixins import ActiveModel


class PastProjectsSheetConfig(ActiveModel, ProjectControlModel):
    """
    Admin-editable configuration for syncing past projects from a Google Sheet.

    Multiple rows may exist but only the active one is used (mirrors the
    single-active pattern in event.CurrentProjectSchedule). The sheet is read
    via the shared core.GoogleCredentialConfig service account.
    """

    name = models.CharField(max_length=255, blank=True, default="", verbose_name="Config Name")
    sheet_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Google Sheet ID",
        help_text="The spreadsheet ID containing project resource rows (the part of the URL after /d/).",
    )
    worksheet_name = models.CharField(
        max_length=255,
        blank=True,
        default="Past-Projects-WEB-LIVE",
        verbose_name="Worksheet Name",
        help_text="The tab/worksheet name to read (e.g. 'Past-Projects-WEB-LIVE').",
    )
    auto_sync_enabled = models.BooleanField(
        default=False,
        verbose_name="Auto Sync",
        help_text="Automatically sync from Google Sheets on a schedule.",
    )
    sync_interval_minutes = models.PositiveIntegerField(
        default=1440,
        verbose_name="Sync Interval (minutes)",
        help_text="How often to auto-sync, in minutes. Used by the sync_past_projects management command.",
    )
    last_synced_at = models.DateTimeField(null=True, blank=True, editable=False)
    sync_error = models.TextField(blank=True, default="")
    sync_count = models.PositiveIntegerField(default=0, editable=False, verbose_name="Projects Synced (last run)")

    class Meta:
        verbose_name = "Project Resource"
        verbose_name_plural = "Project Resources"

    def __str__(self):
        return self.name or "Not configured"

    def save(self, **kwargs):
        # Serialize concurrent activations so the single-active invariant holds:
        # lock the currently-active rows, deactivate them, then activate self —
        # all in one transaction. select_for_update is a no-op on SQLite (dev).
        if self.is_active:
            with transaction.atomic():
                list(PastProjectsSheetConfig.objects.select_for_update().filter(is_active=True).exclude(pk=self.pk))
                PastProjectsSheetConfig.objects.filter(is_active=True).exclude(pk=self.pk).update(is_active=False)
                super().save(**kwargs)
        else:
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
