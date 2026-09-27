from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import ProjectControlModel


class RegistrationSheetSyncConfig(ProjectControlModel):
    class SyncMode(models.TextChoices):
        AUTOMATIC = "automatic", "Automatic"
        INTERVAL = "interval", "Batch changes at intervals"
        MANUAL = "manual", "Manual only"

    class State(models.TextChoices):
        IDLE = "idle", "Idle"
        SCHEDULED = "scheduled", "Scheduled"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        BLOCKED = "blocked", "Needs attention"
        FAILED = "failed", "Failed"

    event = models.OneToOneField("event.Event", on_delete=models.CASCADE, related_name="registration_sheet_sync_config")
    sync_mode = models.CharField(max_length=12, choices=SyncMode.choices, default=SyncMode.AUTOMATIC)
    debounce_seconds = models.PositiveIntegerField(
        default=15, validators=[MinValueValidator(1), MaxValueValidator(3600)]
    )
    max_delay_seconds = models.PositiveIntegerField(
        default=60, validators=[MinValueValidator(1), MaxValueValidator(3600)]
    )
    interval_minutes = models.PositiveIntegerField(
        default=5, validators=[MinValueValidator(1), MaxValueValidator(1440)]
    )
    header_row = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(1000)])
    field_settings = models.JSONField(default=dict, blank=True)
    column_mappings = models.JSONField(default=dict, blank=True)
    requested_generation = models.PositiveBigIntegerField(default=0, editable=False)
    completed_generation = models.PositiveBigIntegerField(default=0, editable=False)
    first_dirty_at = models.DateTimeField(null=True, blank=True, editable=False)
    last_dirty_at = models.DateTimeField(null=True, blank=True, editable=False)
    next_sync_at = models.DateTimeField(null=True, blank=True, editable=False)
    pending_job = models.ForeignKey(
        "core.BackgroundJob", on_delete=models.SET_NULL, null=True, blank=True, editable=False
    )
    state = models.CharField(max_length=12, choices=State.choices, default=State.IDLE, editable=False)
    last_attempt_at = models.DateTimeField(null=True, blank=True, editable=False)
    last_success_at = models.DateTimeField(null=True, blank=True, editable=False)
    last_error = models.TextField(blank=True, default="", editable=False)
    last_added_count = models.PositiveIntegerField(default=0, editable=False)
    last_updated_count = models.PositiveIntegerField(default=0, editable=False)
    last_unchanged_count = models.PositiveIntegerField(default=0, editable=False)
    last_conflict_count = models.PositiveIntegerField(default=0, editable=False)
    last_deleted_count = models.PositiveIntegerField(default=0, editable=False)
    last_header_changes_count = models.PositiveIntegerField(default=0, editable=False)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(debounce_seconds__gte=1), name="event_sync_debounce_positive"),
            models.CheckConstraint(
                condition=models.Q(max_delay_seconds__gte=models.F("debounce_seconds")),
                name="event_sync_delay_gte_debounce",
            ),
            models.CheckConstraint(condition=models.Q(interval_minutes__gte=1), name="event_sync_interval_positive"),
            models.CheckConstraint(condition=models.Q(header_row__gte=1), name="event_sync_header_positive"),
            models.CheckConstraint(
                condition=models.Q(completed_generation__lte=models.F("requested_generation")),
                name="event_sync_generation_order",
            ),
        ]

    def __str__(self):
        return f"Registration sheet sync: {self.event}"

    def clean(self):
        super().clean()
        errors = {}
        if self.max_delay_seconds < self.debounce_seconds:
            errors["max_delay_seconds"] = "Maximum delay must be at least the debounce delay."
        if not isinstance(self.field_settings, dict):
            errors["field_settings"] = "Field settings must be an object."
        elif any(
            not isinstance(key, str)
            or not isinstance(options, dict)
            or set(options) - {"enabled", "label"}
            or ("enabled" in options and not isinstance(options["enabled"], bool))
            or ("label" in options and (not isinstance(options["label"], str) or len(options["label"]) > 500))
            for key, options in self.field_settings.items()
        ):
            errors["field_settings"] = "Each field accepts an enabled checkbox and a label of at most 500 characters."
        if not isinstance(self.column_mappings, dict) or any(
            not isinstance(key, str)
            or not isinstance(column, int)
            or isinstance(column, bool)
            or not 1 <= column <= 18278
            for key, column in self.column_mappings.items()
        ):
            errors["column_mappings"] = "Column mappings must map field keys to column numbers from 1 to 18278."
        elif len(set(self.column_mappings.values())) != len(self.column_mappings):
            errors["column_mappings"] = "Each mapped field must use a different column."
        if errors:
            raise ValidationError(errors)


class RegistrationSheetSyncRecord(ProjectControlModel):
    """A durable receipt or deletion marker, surviving registration deletion."""

    event = models.ForeignKey("event.Event", on_delete=models.CASCADE, related_name="registration_sheet_records")
    registration_id = models.UUIDField()
    synced_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["event", "registration_id"], name="event_sheet_registration_receipt_unique"
            ),
        ]

    def __str__(self):
        return str(self.registration_id)
