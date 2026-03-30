from django.db import models


class EmailServiceConfig(models.Model):
    """
    Singleton model for email delivery configuration.

    Stores AWS SES credentials (primary) and SMTP settings (fallback).
    Managed via Django admin under Site Settings.
    """

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
        verbose_name_plural = "Email Service Config"

    def __str__(self):
        if self.ses_access_key_id:
            return f"Email: SES ({self.ses_region}) + SMTP fallback"
        return f"Email: SMTP ({self.smtp_host})"

    # noinspection PyAttributeOutsideInit
    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        """Load the singleton instance, creating it with defaults if needed."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def source_address(self):
        """Formatted sender address for email headers."""
        if self.ses_from_name:
            return f"{self.ses_from_name} <{self.ses_from_email}>"
        return self.ses_from_email

    @property
    def ses_configured(self):
        return bool(self.ses_access_key_id and self.ses_secret_access_key)


class SMSServiceConfig(models.Model):
    """
    Singleton model for Twilio SMS verification configuration.

    Stores Twilio Verify API credentials. Managed via Django admin
    under Site Settings.
    """

    account_sid = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name="Account SID",
        help_text="Twilio Account SID (starts with AC).",
    )
    auth_token = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name="Auth Token",
    )
    verify_sid = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name="Verify Service SID",
        help_text="Twilio Verify Service SID (starts with VA).",
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "SMS Service Config"
        verbose_name_plural = "SMS Service Config"

    def __str__(self):
        if self.account_sid:
            return f"SMS: Twilio (SID: ...{self.account_sid[-4:]})"
        return "SMS: Not configured"

    # noinspection PyAttributeOutsideInit
    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        """Load the singleton instance, creating it with defaults if needed."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def is_configured(self):
        return bool(self.account_sid and self.auth_token and self.verify_sid)
