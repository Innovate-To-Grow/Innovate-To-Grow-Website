from django.db import models
from django.utils import timezone


class Prospect(models.Model):
    """
    Prospect model for users who might be interested in events but are not members yet.
    """
    # Basic info
    first_name = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="First name (optional)",
        verbose_name="First Name"
    )

    last_name = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Last name (optional)",
        verbose_name="Last Name"
    )

    # Primary email
    email = models.EmailField(
        unique=True,
        help_text="Primary email address",
        verbose_name="Email"
    )

    # Secondary email
    secondary_email = models.EmailField(
        null=True,
        blank=True,
        help_text="Secondary email address (optional)",
        verbose_name="Secondary Email"
    )

    # Phone number
    phone_number = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        help_text="Phone number (optional)",
        verbose_name="Phone Number"
    )

    # Timestamps
    when_input = models.DateTimeField(
        auto_now_add=True,
        help_text="When this prospect was first input",
        verbose_name="When Input?"
    )

    when_signed_up_as_member = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this prospect signed up as a member",
        verbose_name="When signed up as member?"
    )

    when_last_checked = models.DateTimeField(
        auto_now=True,
        help_text="When this prospect was last checked",
        verbose_name="When last checked?"
    )

    # Primary email bounce/collision
    primary_bounced_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the primary email bounced",
        verbose_name="Bounced (when)?"
    )

    primary_collision = models.BooleanField(
        default=False,
        help_text="Whether primary email collides with existing member",
        verbose_name="Collision?"
    )

    # Secondary email bounce/collision
    secondary_bounced_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the secondary email bounced",
        verbose_name="Secondary Bounced (when)?"
    )

    secondary_collision = models.BooleanField(
        default=False,
        help_text="Whether secondary email collides with existing member",
        verbose_name="Secondary Collision"
    )

    # Phone bounce/collision
    phone_bounced_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the phone number bounced",
        verbose_name="Phone Bounced (when)?"
    )

    phone_collision = models.BooleanField(
        default=False,
        help_text="Whether phone number collides with existing member",
        verbose_name="Phone Collision"
    )

    # Notes
    notes = models.TextField(
        blank=True,
        help_text="Additional notes about this prospect",
        verbose_name="Notes"
    )

    class Meta:
        verbose_name = "Prospect"
        verbose_name_plural = "Prospects"
        ordering = ['-when_input']
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['when_input']),
            models.Index(fields=['when_signed_up_as_member']),
            models.Index(fields=['primary_collision']),
        ]

    def __str__(self):
        name = f"{self.first_name} {self.last_name}".strip() if self.first_name or self.last_name else "Unknown"
        return f"{name} ({self.email})"

    def mark_as_member(self):
        """
        Mark this prospect as having signed up as a member.
        """
        if not self.when_signed_up_as_member:
            self.when_signed_up_as_member = timezone.now()
            self.save(update_fields=['when_signed_up_as_member'])
