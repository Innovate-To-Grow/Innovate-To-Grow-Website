from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.utils.text import slugify

from apps.core.models import ProjectControlModel


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
    ticket_login_validity_days = models.PositiveSmallIntegerField(
        default=30,
        validators=[MinValueValidator(1), MaxValueValidator(90)],
        verbose_name="Ticket login link validity (days)",
        help_text="How long the login link in each ticket confirmation email stays valid (1-90 days).",
    )
    ticket_login_reusable = models.BooleanField(
        default=True,
        verbose_name="Reusable ticket login links",
        help_text=(
            "Allow attendees to sign in with their ticket email link repeatedly until it expires. "
            "Off: each link works exactly once. Checked at login time, so unticking it later "
            "immediately blocks further reuse of links already used for this event."
        ),
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
        update_fields = kwargs.get("update_fields")
        will_demote = self.is_live and (update_fields is None or "is_live" in update_fields)
        # Promote-self and demote-others must be atomic and serialized, or two
        # concurrent live-promotions can interleave and leave zero live events
        # (each demotes the other). The lock serializes promotions; no-op on SQLite.
        with transaction.atomic():
            if will_demote:
                list(Event.objects.select_for_update().filter(is_live=True).exclude(pk=self.pk))
            super().save(*args, **kwargs)
            if will_demote:
                Event.objects.exclude(pk=self.pk).filter(is_live=True).update(is_live=False)
