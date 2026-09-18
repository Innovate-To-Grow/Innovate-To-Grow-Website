from django.core.exceptions import ValidationError
from django.db import models, transaction

from apps.core.models import ProjectControlModel
from apps.core.models.mixins import ActiveModel


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
        default=False,
        verbose_name="Auto Sync",
        help_text=(
            "Automatically sync this schedule from its Google Sheet on a schedule "
            "(applies to every schedule, not only the active one — switch it off for archived years)."
        ),
    )
    sync_interval_minutes = models.PositiveIntegerField(
        default=60,
        verbose_name="Sync Interval (minutes)",
        help_text="How often to auto-sync, in minutes. Used by the sync_schedule management command.",
    )

    class Meta:
        verbose_name = "Current Project and Schedule"
        verbose_name_plural = "Current Project and Schedule"
        constraints = [
            models.UniqueConstraint(
                fields=["is_active"],
                condition=models.Q(is_active=True),
                name="event_one_active_schedule",
            ),
        ]

    def __str__(self):
        return self.name or "Not configured"

    def validate_constraints(self, exclude=None):
        # save() replaces the active row atomically (and archives the others),
        # so a one-step activation must not be rejected during ModelForm
        # validation; the database still enforces the single-active constraint.
        exclude = set(exclude or ())
        if self.is_active:
            exclude.add("is_active")
        super().validate_constraints(exclude=exclude)

    def save(self, **kwargs):
        # Serialize concurrent activations so the single-active invariant holds:
        # lock the currently-active rows, deactivate them, then activate self —
        # all in one transaction. select_for_update is a no-op on SQLite (dev).
        # Auto-sync applies to every row (each has its own sheet), so a row that
        # stops being active — archived by another row's activation or
        # deactivated explicitly — also stops auto-syncing; an admin re-enables
        # it on a past schedule deliberately rather than inheriting it from when
        # that row was the live one.
        if self.is_active:
            with transaction.atomic():
                list(CurrentProjectSchedule.objects.select_for_update().filter(is_active=True).exclude(pk=self.pk))
                CurrentProjectSchedule.objects.filter(is_active=True).exclude(pk=self.pk).update(
                    is_active=False, auto_sync_enabled=False
                )
                super().save(**kwargs)
            return

        if self.auto_sync_enabled and self._is_being_deactivated():
            self.auto_sync_enabled = False
            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                kwargs["update_fields"] = {*update_fields, "auto_sync_enabled"}
        super().save(**kwargs)

    def _is_being_deactivated(self) -> bool:
        if self._state.adding or not self.pk:
            return False
        return CurrentProjectSchedule.objects.filter(pk=self.pk, is_active=True).exists()

    @classmethod
    def load(cls):
        """Return the active config, or None if no active config exists."""
        try:
            return cls.objects.get(is_active=True)
        except cls.DoesNotExist:
            return None

    @classmethod
    def load_by_id(cls, raw_id):
        """Return the schedule with this id (active or not), or None for unknown/malformed ids."""
        if not raw_id:
            return None
        try:
            return cls.objects.filter(pk=raw_id).first()
        except (TypeError, ValueError, ValidationError):
            return None

    @property
    def sync_is_due(self) -> bool:
        """True when auto-sync is enabled and the interval has elapsed since the last attempt.

        A failed auto-sync counts as an attempt, so a broken or unshared sheet
        is retried once per interval instead of on every cron tick.
        """
        if not self.auto_sync_enabled:
            return False
        last_attempt = max(filter(None, (self.last_synced_at, self._last_auto_sync_attempt_at())), default=None)
        if last_attempt is None:
            return True
        from django.utils import timezone

        elapsed = (timezone.now() - last_attempt).total_seconds()
        return elapsed >= self.sync_interval_minutes * 60

    def _last_auto_sync_attempt_at(self):
        if self._state.adding:
            return None
        from .sync_log import ScheduleSyncLog

        return (
            self.sync_logs.filter(sync_type=ScheduleSyncLog.SyncType.AUTO)
            .order_by("-created_at")
            .values_list("created_at", flat=True)
            .first()
        )


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
