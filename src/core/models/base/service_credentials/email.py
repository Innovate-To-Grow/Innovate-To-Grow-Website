from django.db import models


class EmailServiceConfig(models.Model):
    """
    Email delivery configuration.

    Stores AWS SES credentials (primary) and SMTP settings (fallback).
    Multiple configs can exist but only one may be active at a time.
    Managed via Django admin under Site Settings.
    """

    name = models.CharField(
        max_length=128,
        default="Default",
        verbose_name="Config Name",
        help_text="A label to identify this configuration (e.g. 'Production SES', 'Dev SMTP').",
    )
    is_active = models.BooleanField(
        default=False,
        verbose_name="Active",
        help_text="Only one config can be active. Activating this will deactivate others.",
    )

    # AWS SES
    ses_access_key_id = models.CharField(
        max_length=128,
        blank=True,
        default="",
        verbose_name="SES Access Key ID",
        help_text="AWS access key for SES. Leave blank to skip SES and use SMTP only.",
    )
    ses_secret_access_key = models.CharField(
        max_length=256,
        blank=True,
        default="",
        verbose_name="SES Secret Access Key",
    )
    ses_region = models.CharField(
        max_length=32,
        blank=True,
        default="us-west-2",
        verbose_name="SES Region",
    )
    ses_from_email = models.CharField(
        max_length=254,
        blank=True,
        default="i2g@g.ucmerced.edu",
        verbose_name="From Email",
        help_text="Sender email address for both SES and SMTP.",
    )
    ses_from_name = models.CharField(
        max_length=128,
        blank=True,
        default="Innovate to Grow",
        verbose_name="From Name",
    )

    ses_max_send_rate = models.PositiveIntegerField(
        default=10,
        verbose_name="Campaign Send Rate (emails/sec)",
        help_text="Max emails per second for bulk campaigns. Keep below SES account limit to leave room for transactional mail.",
    )

    # SMTP fallback
    smtp_host = models.CharField(
        max_length=254,
        blank=True,
        default="smtp.gmail.com",
        verbose_name="SMTP Host",
    )
    smtp_port = models.PositiveIntegerField(
        default=587,
        verbose_name="SMTP Port",
    )
    smtp_use_tls = models.BooleanField(
        default=True,
        verbose_name="SMTP Use TLS",
    )
    smtp_username = models.CharField(
        max_length=254,
        blank=True,
        default="",
        verbose_name="SMTP Username",
    )
    smtp_password = models.CharField(
        max_length=256,
        blank=True,
        default="",
        verbose_name="SMTP Password",
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Email Service Config"
        verbose_name_plural = "Email Service Configs"

    def __str__(self):
        status = " (active)" if self.is_active else ""
        if self.ses_access_key_id:
            return f"{self.name}: SES ({self.ses_region}) + SMTP fallback{status}"
        return f"{self.name}: SMTP ({self.smtp_host}){status}"

    def save(self, *args, **kwargs):
        if self.is_active:
            EmailServiceConfig.objects.filter(is_active=True).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        """Load the active config, falling back to the most recently updated one.

        Returns an unsaved instance with defaults when no rows exist so that
        callers can safely access properties like ``ses_configured`` without
        guarding against ``None``.
        """
        obj = cls.objects.filter(is_active=True).first()
        if obj is None:
            obj = cls.objects.order_by("-updated_at").first()
        return obj if obj is not None else cls()

    @property
    def source_address(self):
        """Formatted sender address for email headers."""
        if self.ses_from_name:
            return f"{self.ses_from_name} <{self.ses_from_email}>"
        return self.ses_from_email

    @property
    def ses_configured(self):
        return bool(self.ses_access_key_id and self.ses_secret_access_key)
