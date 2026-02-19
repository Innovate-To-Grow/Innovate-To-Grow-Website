"""
Event model for hierarchical event structure.
"""

from datetime import date as date_cls
from datetime import datetime
from datetime import time as time_cls

from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from core.models import ProjectControlModel


class Event(ProjectControlModel):
    """Core event model containing basic info and markdown bullet points."""

    # Basic Info
    event_name = models.CharField(max_length=255, help_text="Name of the event.")
    event_date_time = models.DateTimeField(help_text="Date of the event.")

    # Markdown bullet points (stored as JSON arrays)
    upper_bullet_points = models.JSONField(
        default=list,
        blank=True,
        help_text="Upper bullet points in Markdown format (array of strings).",
    )
    lower_bullet_points = models.JSONField(
        default=list,
        blank=True,
        help_text="Lower bullet points in Markdown format (array of strings).",
    )

    # Expo and Reception tables (stored as JSON arrays)
    expo_table = models.JSONField(
        default=list,
        blank=True,
        help_text="Expo table rows: [{time, room, description}]",
    )
    reception_table = models.JSONField(
        default=list,
        blank=True,
        help_text="Reception table rows: [{time, room, description}]",
    )

    # Special awards (stored as JSON array of strings)
    special_awards = models.JSONField(
        default=list,
        blank=True,
        help_text="Special awards as array of strings (e.g., ['Award 1', 'Award 2']).",
    )

    # Publishing
    is_published = models.BooleanField(
        default=False,
        help_text="Whether this event is published and visible.",
    )

    # Multi-event archive fields
    slug = models.SlugField(
        max_length=255,
        unique=True,
        help_text="Unique slug identifier for the event (e.g., 'spring-expo-2026').",
    )
    is_live = models.BooleanField(
        default=False,
        help_text="Whether this event is currently live (only one event can be live at a time).",
    )

    def __init__(self, *args, **kwargs):
        # Backward compatibility: older callers/tests still pass event_date + event_time.
        legacy_event_date = kwargs.pop("event_date", None)
        legacy_event_time = kwargs.pop("event_time", None)
        super().__init__(*args, **kwargs)

        if legacy_event_date is not None:
            self.event_date = legacy_event_date
        if legacy_event_time is not None:
            self.event_time = legacy_event_time

    @property
    def event_uuid(self):
        return self.id

    @staticmethod
    def _coerce_date(value):
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date_cls):
            return value
        if isinstance(value, str):
            return date_cls.fromisoformat(value)
        raise TypeError(f"Unsupported event_date type: {type(value)!r}")

    @staticmethod
    def _coerce_time(value):
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.time().replace(tzinfo=None)
        if isinstance(value, time_cls):
            return value.replace(tzinfo=None)
        if isinstance(value, str):
            normalized = value.strip()
            if normalized.endswith("Z"):
                normalized = f"{normalized[:-1]}+00:00"
            if "T" in normalized:
                return datetime.fromisoformat(normalized).time().replace(tzinfo=None)
            return time_cls.fromisoformat(normalized).replace(tzinfo=None)
        raise TypeError(f"Unsupported event_time type: {type(value)!r}")

    def _apply_event_datetime_parts(self, *, new_date=None, new_time=None):
        if self.event_date_time is not None:
            current_dt = self.event_date_time
            if timezone.is_aware(current_dt):
                current_dt = timezone.localtime(current_dt, timezone.get_current_timezone())
            current_date = current_dt.date()
            current_time = current_dt.time().replace(tzinfo=None)
        else:
            now = timezone.localtime(timezone.now(), timezone.get_current_timezone())
            current_date = now.date()
            current_time = now.time().replace(tzinfo=None)

        final_date = new_date if new_date is not None else current_date
        final_time = new_time if new_time is not None else current_time
        combined = datetime.combine(final_date, final_time)
        self.event_date_time = timezone.make_aware(combined, timezone.get_current_timezone())

    @property
    def event_date(self):
        if self.event_date_time is None:
            return None
        current_dt = self.event_date_time
        if timezone.is_aware(current_dt):
            current_dt = timezone.localtime(current_dt, timezone.get_current_timezone())
        return current_dt.date()

    @event_date.setter
    def event_date(self, value):
        self._apply_event_datetime_parts(new_date=self._coerce_date(value))

    @property
    def event_time(self):
        if self.event_date_time is None:
            return None
        current_dt = self.event_date_time
        if timezone.is_aware(current_dt):
            current_dt = timezone.localtime(current_dt, timezone.get_current_timezone())
        return current_dt.time().replace(tzinfo=None)

    @event_time.setter
    def event_time(self, value):
        self._apply_event_datetime_parts(new_time=self._coerce_time(value))

    def _ensure_slug(self):
        if self.slug:
            return
        base_slug = slugify(self.event_name) or "event"
        candidate = base_slug
        counter = 1
        while Event.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
            candidate = f"{base_slug}-{counter}"
            counter += 1
        self.slug = candidate

    def save(self, *args, **kwargs):
        self._ensure_slug()
        super().save(*args, **kwargs)

    def delete(self, using=None, keep_parents=False):
        """
        Soft-delete event and explicitly clear dependent rows.

        Event uses soft delete, so DB-level CASCADE doesn't fire automatically.
        """
        self.programs.all().delete()
        self.track_winners.all().delete()
        self.special_award_winners.all().delete()
        super().delete(using=using, keep_parents=keep_parents)

    def __str__(self):
        event_date = self.event_date.isoformat() if self.event_date else "unknown-date"
        return f"{self.event_name} ({event_date})"

    class Meta:
        ordering = ["-event_date_time", "-created_at"]
        verbose_name = "Event"
        verbose_name_plural = "Events"
