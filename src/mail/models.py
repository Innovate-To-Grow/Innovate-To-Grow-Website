"""
Models for the mail app — Gmail and SES sender configuration plus audit logs.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import ProjectControlModel


class GoogleAccount(ProjectControlModel):
    """
    Stores Gmail API service account credentials for Domain-Wide Delegation.

    One account can be marked as active at a time. The service account JSON
    from Google Cloud Console is stored and used to authenticate via the
    Gmail API with delegated access.
    """

    email = models.EmailField(
        unique=True,
        help_text="Delegated Gmail address (e.g. i2g@g.ucmerced.edu)",
    )
    display_name = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text='Sender display name (e.g. "Innovate to Grow")',
    )
    service_account_json = models.TextField(
        help_text="Full service account JSON key from Google Cloud Console",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Only one account can be active at a time.",
    )

    # Operational metadata
    last_used_at = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
        help_text="Last time this account was used for a Gmail API call.",
    )
    last_error = models.TextField(
        blank=True,
        default="",
        help_text="Last error message from Gmail API.",
    )

    class Meta:
        ordering = ["-is_active", "-created_at"]
        verbose_name = "Gmail API Account"
        verbose_name_plural = "Gmail API Accounts"

    def __str__(self):
        label = self.display_name or self.email
        parts = [label]
        if not self.is_active:
            parts.append("[Inactive]")
        return " ".join(parts)

    def save(self, *args, **kwargs):
        """Ensure only one account is active at a time."""
        if self.is_active:
            GoogleAccount.objects.filter(is_active=True).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

    @classmethod
    def get_active(cls):
        """Return the active account, or None."""
        return cls.objects.filter(is_active=True).first()

    def mark_used(self, error=""):
        """Update operational metadata after a Gmail API call."""
        self.last_used_at = timezone.now()
        self.last_error = error or ""
        self.save(update_fields=["last_used_at", "last_error", "updated_at"])


class EmailLog(ProjectControlModel):
    """
    Audit log for Gmail API operations performed through the admin.
    """

    class Action(models.TextChoices):
        SEND = "send", "Send"
        REPLY = "reply", "Reply"
        FORWARD = "forward", "Forward"
        READ = "read", "Read"
        DELETE = "delete", "Delete"
        LABEL = "label", "Label"

    class Status(models.TextChoices):
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    account = models.ForeignKey(
        GoogleAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="email_logs",
    )
    action = models.CharField(
        max_length=10,
        choices=Action.choices,
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
    )
    gmail_message_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )
    subject = models.CharField(
        max_length=500,
        blank=True,
        default="",
    )
    recipients = models.TextField(
        blank=True,
        default="",
        help_text="Comma-separated list of recipients.",
    )
    error_message = models.TextField(
        blank=True,
        default="",
    )
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mail_logs",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Email Log"
        verbose_name_plural = "Email Logs"
        indexes = [
            models.Index(fields=["action", "status"]),
            models.Index(fields=["account", "created_at"]),
        ]

    def __str__(self):
        return f"{self.get_action_display()} - {self.subject[:50] or '(no subject)'}"


class SESAccount(ProjectControlModel):
    """
    Stores the single SES sender configuration exposed in Django Admin.

    AWS credentials live in environment variables; this model only controls
    whether the sender is enabled and tracks operational metadata.
    """

    email = models.EmailField(
        default="i2g@g.ucmerced.edu",
        help_text="Fixed SES sender identity used by the new I2G system.",
    )
    display_name = models.CharField(
        max_length=128,
        blank=True,
        default="Innovate to Grow",
        help_text='Sender display name (for example "Innovate to Grow").',
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Disable to temporarily block SES sends from the admin.",
    )
    last_used_at = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
        help_text="Last time this SES sender successfully attempted a send.",
    )
    last_error = models.TextField(
        blank=True,
        default="",
        help_text="Last SES error encountered during send.",
    )

    class Meta:
        ordering = ["-is_active", "-created_at"]
        verbose_name = "SES Mail Sender"
        verbose_name_plural = "SES Mail Senders"

    def __str__(self):
        label = self.display_name or self.email
        parts = [label]
        if not self.is_active:
            parts.append("[Inactive]")
        return " ".join(parts)

    def save(self, *args, **kwargs):
        """Keep the sender identity fixed and allow only one active record."""
        self.email = "i2g@g.ucmerced.edu"
        if self.is_active:
            SESAccount.objects.filter(is_active=True).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

    @classmethod
    def get_active(cls):
        """Return the active SES sender, or None."""
        return cls.objects.filter(is_active=True).first()

    def mark_used(self, error=""):
        """Update operational metadata after an SES API call."""
        self.last_used_at = timezone.now()
        self.last_error = error or ""
        self.save(update_fields=["last_used_at", "last_error", "updated_at"])


class SESEmailLog(ProjectControlModel):
    """Audit log for SES sends performed through the admin."""

    class Action(models.TextChoices):
        SEND = "send", "Send"

    class Status(models.TextChoices):
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    account = models.ForeignKey(
        SESAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="email_logs",
    )
    action = models.CharField(
        max_length=10,
        choices=Action.choices,
        default=Action.SEND,
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
    )
    ses_message_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )
    subject = models.CharField(
        max_length=500,
        blank=True,
        default="",
    )
    recipients = models.TextField(
        blank=True,
        default="",
        help_text="Comma-separated list of recipients.",
    )
    error_message = models.TextField(
        blank=True,
        default="",
    )
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ses_mail_logs",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "SES Email Log"
        verbose_name_plural = "SES Email Logs"
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["account", "created_at"]),
        ]

    def __str__(self):
        return f"{self.get_action_display()} - {self.subject[:50] or '(no subject)'}"
