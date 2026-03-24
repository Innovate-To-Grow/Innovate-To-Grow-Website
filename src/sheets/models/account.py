from django.db import models
from django.utils import timezone

from core.models import ProjectControlModel


class SheetsAccount(ProjectControlModel):
    """
    Stores Google Sheets API service account credentials.

    One account can be marked as active at a time. The service account JSON
    from Google Cloud Console is stored and used to authenticate via the
    Google Sheets API.
    """

    email = models.EmailField(
        unique=True,
        help_text="Service account email (e.g. sheets-sync@project.iam.gserviceaccount.com)",
    )
    display_name = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text='Display name (e.g. "I2G Sheets Sync")',
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
        help_text="Last time this account was used for a Sheets API call.",
    )
    last_error = models.TextField(
        blank=True,
        default="",
        help_text="Last error message from Sheets API.",
    )

    class Meta:
        ordering = ["-is_active", "-created_at"]
        verbose_name = "Sheets API Account"
        verbose_name_plural = "Sheets API Accounts"

    def __str__(self):
        label = self.display_name or self.email
        parts = [label]
        if not self.is_active:
            parts.append("[Inactive]")
        return " ".join(parts)

    def save(self, *args, **kwargs):
        """Ensure only one account is active at a time."""
        if self.is_active:
            SheetsAccount.objects.filter(is_active=True).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

    @classmethod
    def get_active(cls):
        """Return the active account, or None."""
        return cls.objects.filter(is_active=True).first()

    def mark_used(self, error=""):
        """Update operational metadata after a Sheets API call."""
        self.last_used_at = timezone.now()
        self.last_error = error or ""
        self.save(update_fields=["last_used_at", "last_error", "updated_at"])
