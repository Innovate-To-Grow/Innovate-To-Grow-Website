"""
Google Gmail Account model for storing SMTP credentials.

Supports multiple Gmail accounts with App Passwords. One account can be
marked as the default sender.
"""

from django.db import models
from django.utils import timezone

from core.models import AuthoredModel, ProjectControlModel


class GoogleGmailAccount(AuthoredModel, ProjectControlModel):
    """
    Stores Gmail SMTP credentials (App Password) in the database.

    One account can be designated as the ``is_default`` sender.  When
    ``send_email()`` is called without an explicit account, the default
    active account is used automatically.
    """

    gmail_address = models.CharField(
        max_length=128,
        unique=True,
        help_text="Google Gmail address (e.g. team@gmail.com)",
    )
    google_app_password = models.TextField(
        help_text="Google App Password (16 characters, spaces ignored)",
    )
    display_name = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text='Sender display name (e.g. "I2G Team")',
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Uncheck to temporarily disable this account.",
    )
    is_default = models.BooleanField(
        default=False,
        help_text="Mark as default sender. Only one account can be default.",
    )

    # SMTP settings (rarely changed)
    smtp_host = models.CharField(
        max_length=128,
        default="smtp.gmail.com",
        help_text="SMTP server hostname.",
    )
    smtp_port = models.PositiveIntegerField(
        default=587,
        help_text="SMTP server port (587 for TLS, 465 for SSL).",
    )
    use_tls = models.BooleanField(
        default=True,
        help_text="Use STARTTLS (port 587). Uncheck for SSL (port 465).",
    )

    # Operational metadata
    last_used_at = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
        help_text="Last time an email was sent from this account.",
    )
    last_error = models.TextField(
        blank=True,
        default="",
        help_text="Last error message when sending failed.",
    )

    class Meta:
        ordering = ["-is_default", "-is_active", "-created_at"]
        verbose_name = "Gmail Account"
        verbose_name_plural = "Gmail Accounts"

    def __str__(self):
        label = self.display_name or self.gmail_address
        parts = [label]
        if self.is_default:
            parts.append("[Default]")
        if not self.is_active:
            parts.append("[Inactive]")
        return " ".join(parts)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def save(self, *args, **kwargs):
        """Ensure only one account is marked as default."""
        if self.is_default:
            GoogleGmailAccount.objects.filter(is_default=True).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)

    # ------------------------------------------------------------------
    # Class helpers
    # ------------------------------------------------------------------

    @classmethod
    def get_default(cls):
        """Return the default active account, or ``None``."""
        return cls.objects.filter(is_default=True, is_active=True, is_deleted=False).first()

    @classmethod
    def get_active_accounts(cls):
        """Return all active, non-deleted accounts."""
        return cls.objects.filter(is_active=True, is_deleted=False)

    # ------------------------------------------------------------------
    # Instance helpers
    # ------------------------------------------------------------------

    def get_from_email(self) -> str:
        """Return RFC-5322 ``"Display Name <addr>"`` string."""
        if self.display_name:
            return f"{self.display_name} <{self.gmail_address}>"
        return self.gmail_address

    def mark_used(self, error: str = ""):
        """Update operational metadata after a send attempt."""
        self.last_used_at = timezone.now()
        self.last_error = error or ""
        self.save(update_fields=["last_used_at", "last_error", "updated_at"])
