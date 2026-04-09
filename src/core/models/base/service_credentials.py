from django.core.exceptions import ValidationError
from django.db import models


def validate_google_credentials_json(value):
    """Validate that the value is a dict with required Google service-account fields."""
    if not isinstance(value, dict):
        raise ValidationError("Credentials must be a JSON object.")
    required = {"type", "project_id", "private_key", "client_email", "token_uri"}
    missing = required - value.keys()
    if missing:
        raise ValidationError(f"Missing required fields: {', '.join(sorted(missing))}")


class GoogleCredentialConfig(models.Model):
    """
    Google service-account credential configuration.

    Stores the contents of a Google Cloud service-account JSON key file.
    Multiple configs can exist but only one may be active at a time.
    Managed via Django admin under Site Settings.
    """

    name = models.CharField(
        max_length=128,
        default="Default",
        verbose_name="Config Name",
        help_text="A label to identify this configuration (e.g. 'Production Sheets', 'Dev Service Account').",
    )
    is_active = models.BooleanField(
        default=False,
        verbose_name="Active",
        help_text="Only one config can be active. Activating this will deactivate others.",
    )

    credentials_json = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Service Account JSON",
        help_text="Paste the full contents of the Google service-account JSON key file.",
        validators=[validate_google_credentials_json],
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Google Credential Config"
        verbose_name_plural = "Google Credential Configs"

    def __str__(self):
        status = " (active)" if self.is_active else ""
        project = self.credentials_json.get("project_id", "unknown") if self.credentials_json else "empty"
        return f"{self.name}: {project}{status}"

    def save(self, *args, **kwargs):
        if self.is_active:
            GoogleCredentialConfig.objects.filter(is_active=True).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        """Load the active config, falling back to the most recently updated one.

        Returns an unsaved instance with defaults when no rows exist so that
        callers can safely access properties like ``is_configured`` without
        guarding against ``None``.
        """
        obj = cls.objects.filter(is_active=True).first()
        if obj is None:
            obj = cls.objects.order_by("-updated_at").first()
        return obj if obj is not None else cls()

    @property
    def is_configured(self):
        return bool(
            self.credentials_json
            and self.credentials_json.get("private_key")
            and self.credentials_json.get("client_email")
        )

    @property
    def project_id(self):
        return self.credentials_json.get("project_id", "") if self.credentials_json else ""

    @property
    def client_email(self):
        return self.credentials_json.get("client_email", "") if self.credentials_json else ""

    def get_credentials_info(self):
        """Return the credentials dict suitable for ``google.oauth2.service_account.Credentials.from_service_account_info()``."""
        return self.credentials_json if self.credentials_json else {}


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


class GmailImportConfig(models.Model):
    """
    Gmail IMAP configuration for importing HTML templates from sent mail.

    Multiple configs can exist but only one may be active at a time.
    Managed via Django admin under Site Settings.
    """

    name = models.CharField(
        max_length=128,
        default="Default",
        verbose_name="Config Name",
        help_text="A label to identify this configuration (e.g. 'Production Gmail Import').",
    )
    is_active = models.BooleanField(
        default=False,
        verbose_name="Active",
        help_text="Only one config can be active. Activating this will deactivate others.",
    )
    imap_host = models.CharField(
        max_length=254,
        blank=True,
        default="imap.gmail.com",
        verbose_name="IMAP Host",
    )
    gmail_username = models.CharField(
        max_length=254,
        blank=True,
        default="",
        verbose_name="Gmail Username",
        help_text="The Gmail account used to log in over IMAP and read sent messages.",
    )
    gmail_password = models.CharField(
        max_length=256,
        blank=True,
        default="",
        verbose_name="Gmail Password",
        help_text="Gmail app password used for IMAP login.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Gmail Import Config"
        verbose_name_plural = "Gmail Import Configs"

    def __str__(self):
        status = " (active)" if self.is_active else ""
        mailbox = self.gmail_username or "unconfigured"
        return f"{self.name}: {mailbox}{status}"

    def save(self, *args, **kwargs):
        if self.is_active:
            GmailImportConfig.objects.filter(is_active=True).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        """Load the active config, falling back to the most recently updated one."""
        obj = cls.objects.filter(is_active=True).first()
        if obj is None:
            obj = cls.objects.order_by("-updated_at").first()
        return obj if obj is not None else cls()

    @property
    def is_configured(self):
        return bool(self.imap_host and self.gmail_username and self.gmail_password)

    @property
    def mailbox(self):
        return self.gmail_username


class SMSServiceConfig(models.Model):
    """
    Twilio SMS verification configuration.

    Stores Twilio Verify API credentials. Multiple configs can exist
    but only one may be active at a time. Managed via Django admin
    under Site Settings.
    """

    name = models.CharField(
        max_length=128,
        default="Default",
        verbose_name="Config Name",
        help_text="A label to identify this configuration.",
    )
    is_active = models.BooleanField(
        default=False,
        verbose_name="Active",
        help_text="Only one config can be active. Activating this will deactivate others.",
    )

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
    from_number = models.CharField(
        max_length=20,
        blank=True,
        default="",
        verbose_name="From Phone Number",
        help_text="Twilio phone number for sending messages (e.g. +1234567890). Used for test SMS.",
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "SMS Service Config"
        verbose_name_plural = "SMS Service Configs"

    def __str__(self):
        status = " (active)" if self.is_active else ""
        if self.account_sid:
            return f"{self.name}: Twilio (SID: ...{self.account_sid[-4:]}){status}"
        return f"{self.name}: Not configured{status}"

    def save(self, *args, **kwargs):
        if self.is_active:
            SMSServiceConfig.objects.filter(is_active=True).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        """Load the active config, falling back to the most recently updated one.

        Returns an unsaved instance with defaults when no rows exist so that
        callers can safely access properties like ``is_configured`` without
        guarding against ``None``.
        """
        obj = cls.objects.filter(is_active=True).first()
        if obj is None:
            obj = cls.objects.order_by("-updated_at").first()
        return obj if obj is not None else cls()

    @property
    def is_configured(self):
        return bool(self.account_sid and self.auth_token and self.verify_sid)
