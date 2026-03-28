from django.db import models
from django.utils import timezone

from core.models import ProjectControlModel


class GoogleAccount(ProjectControlModel):
    """Stores Gmail API service account credentials for delegated Gmail access."""

    email = models.EmailField(unique=True, help_text="Delegated Gmail address (e.g. i2g@g.ucmerced.edu)")
    display_name = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text='Sender display name (e.g. "Innovate to Grow")',
    )
    service_account_json = models.TextField(help_text="Full service account JSON key from Google Cloud Console")
    is_active = models.BooleanField(default=True, help_text="Only one account can be active at a time.")
    last_used_at = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
        help_text="Last time this account was used for a Gmail API call.",
    )
    last_error = models.TextField(blank=True, default="", help_text="Last error message from Gmail API.")

    class Meta:
        ordering = ["-is_active", "-created_at"]
        verbose_name = "Gmail API Account"
        verbose_name_plural = "Gmail API Accounts"

    def __str__(self):
        label = self.display_name or self.email
        return f"{label} [Inactive]" if not self.is_active else label

    def save(self, *args, **kwargs):
        if self.is_active:
            GoogleAccount.objects.filter(is_active=True).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

    @classmethod
    def get_active(cls):
        return cls.objects.filter(is_active=True).first()

    def mark_used(self, error=""):
        self.last_used_at = timezone.now()
        self.last_error = error or ""
        self.save(update_fields=["last_used_at", "last_error", "updated_at"])


class SESAccount(ProjectControlModel):
    """Stores the fixed SES sender configuration exposed in Django admin."""

    email = models.EmailField(
        default="i2g@g.ucmerced.edu", help_text="Fixed SES sender identity used by the new I2G system."
    )
    display_name = models.CharField(
        max_length=128,
        blank=True,
        default="Innovate to Grow",
        help_text='Sender display name (for example "Innovate to Grow").',
    )
    is_active = models.BooleanField(default=True, help_text="Disable to temporarily block SES sends from the admin.")
    last_used_at = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
        help_text="Last time this SES sender successfully attempted a send.",
    )
    last_error = models.TextField(blank=True, default="", help_text="Last SES error encountered during send.")

    class Meta:
        ordering = ["-is_active", "-created_at"]
        verbose_name = "SES Mail Sender"
        verbose_name_plural = "SES Mail Senders"

    def __str__(self):
        label = self.display_name or self.email
        return f"{label} [Inactive]" if not self.is_active else label

    def save(self, *args, **kwargs):
        self.email = "i2g@g.ucmerced.edu"
        if self.is_active:
            SESAccount.objects.filter(is_active=True).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

    @classmethod
    def get_active(cls):
        return cls.objects.filter(is_active=True).first()

    def mark_used(self, error=""):
        self.last_used_at = timezone.now()
        self.last_error = error or ""
        self.save(update_fields=["last_used_at", "last_error", "updated_at"])
