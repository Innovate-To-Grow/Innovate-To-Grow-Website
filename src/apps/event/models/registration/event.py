from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify

from core.models import ProjectControlModel


class Event(ProjectControlModel):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    date = models.DateField()
    location = models.CharField(max_length=255)
    description = models.TextField()
    is_live = models.BooleanField(default=False)
    allow_secondary_email = models.BooleanField(
        default=False,
        help_text="Prompt registrants to enter a secondary email address.",
    )
    collect_phone = models.BooleanField(
        default=False,
        help_text="Show a phone number field on the registration form.",
    )
    verify_phone = models.BooleanField(
        default=False,
        help_text="Require phone number verification via SMS code. Only applies when phone collection is enabled.",
    )

    # Google Sheets sync (registration data — separate from the schedule sheet on CurrentProjectSchedule)
    registration_sheet_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Registration Google Sheet ID",
        help_text="The ID of the Google Sheet used to sync event registration data.",
    )
    registration_sheet_gid = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        verbose_name="Registration Worksheet GID",
        help_text="The GID of the worksheet within the registration sheet.",
    )
    registration_sheet_synced_at = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
        verbose_name="Last Sheet Sync",
    )
    registration_sheet_sync_count = models.PositiveIntegerField(
        default=0,
        editable=False,
        verbose_name="Last Sync Row Count",
    )
    registration_sheet_sync_error = models.TextField(
        blank=True,
        default="",
        editable=False,
        verbose_name="Last Sync Error",
    )

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.verify_phone and not self.collect_phone:
            raise ValidationError({"verify_phone": "Cannot verify phone without collecting it."})

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
        update_fields = kwargs.get("update_fields")
        if self.is_live and (update_fields is None or "is_live" in update_fields):
            Event.objects.exclude(pk=self.pk).filter(is_live=True).update(is_live=False)
