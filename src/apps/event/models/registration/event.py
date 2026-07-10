from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.text import slugify

from apps.core.models import ProjectControlModel


class Event(ProjectControlModel):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    date = models.DateField(verbose_name="Start date")
    end_date = models.DateField(verbose_name="End date")
    location = models.CharField(max_length=255)
    description = models.TextField()
    registration_open = models.BooleanField(
        default=False,
        verbose_name="Registration open",
        help_text="Allow this event to appear in public registration and accept new registrations.",
    )
    allow_secondary_email = models.BooleanField(
        default=False,
        help_text="Prompt registrants to enter a secondary email address.",
    )
    collect_phone = models.BooleanField(
        default=False,
        verbose_name="Prompt for Phone Number",
        help_text="Prompt registrants to enter a phone number on the registration form.",
    )
    verify_phone = models.BooleanField(
        default=False,
        help_text=(
            "Require phone number verification via SMS code. Only available when Prompt for Phone Number is enabled."
        ),
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
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("date")),
                name="event_end_date_gte_start_date",
            ),
            models.CheckConstraint(
                condition=models.Q(collect_phone=True) | models.Q(verify_phone=False),
                name="event_verify_phone_requires_prompt",
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def effective_end_date(self):
        """Return a safe inclusive end date during the rolling migration window."""
        return self.end_date or self.date

    def clean_fields(self, exclude=None):
        # Rows written by the previous application revision have a null
        # ``end_date`` during the expand phase. Normalize a loaded row before
        # full_clean() so CLI/System Intelligence can safely update unrelated
        # fields and persist the single-day range.
        excluded = set(exclude or ())
        if not self._state.adding and "end_date" not in excluded and self.end_date is None and self.date is not None:
            self.end_date = self.date
        super().clean_fields(exclude=exclude)

    def clean(self):
        super().clean()
        if self.date and self.end_date and self.end_date < self.date:
            raise ValidationError({"end_date": "End date cannot be before start date."})
        if self.verify_phone and not self.collect_phone:
            raise ValidationError({"verify_phone": "Cannot verify phone without prompting for a phone number."})

    def save(self, *args, **kwargs):
        if self.end_date is None and self.date is not None:
            self.end_date = self.date
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = {*kwargs["update_fields"], "end_date"}
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
