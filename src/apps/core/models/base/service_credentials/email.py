from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import models, transaction

from ..control import ProjectControlModel


class EmailServiceConfig(models.Model):
    """
    Email delivery configuration.

    AWS SES credentials and region live on ``AWSCredentialConfig``; this model
    stores email-specific settings like sender address and campaign
    throughput. Multiple configs can exist but only one may be active at a
    time.
    """

    class Provider(models.TextChoices):
        SES = "ses", "AWS SES"
        SMTP = "smtp", "SMTP"

    name = models.CharField(
        max_length=128,
        default="Default",
        verbose_name="Config Name",
        help_text="A label to identify this configuration (e.g. 'Production SES', 'Dev SES').",
    )
    is_active = models.BooleanField(
        default=False,
        verbose_name="Active",
        help_text="Only one config can be active. Activating this will deactivate others.",
    )
    provider = models.CharField(
        max_length=16,
        choices=Provider.choices,
        default=Provider.SES,
        help_text="Email delivery provider used by this configuration.",
    )

    from_email = models.CharField(
        max_length=254,
        blank=True,
        default="i2g@g.ucmerced.edu",
        verbose_name="From Email",
        help_text="Sender email address used for outgoing email.",
    )
    from_name = models.CharField(
        max_length=128,
        blank=True,
        default="Innovate to Grow",
        verbose_name="From Name",
    )

    max_send_rate = models.PositiveIntegerField(
        default=10,
        verbose_name="Campaign Send Rate (emails/sec)",
        help_text="Max emails per second for bulk campaigns. Keep below SES account limit to leave room for transactional mail.",
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Email Service Config"
        verbose_name_plural = "Email Service Configs"
        constraints = [
            models.UniqueConstraint(
                fields=["is_active"],
                condition=models.Q(is_active=True),
                name="core_one_active_email_config",
            ),
        ]

    def __str__(self):
        status = " (active)" if self.is_active else ""
        provider = self.get_provider_display()
        configured = self.delivery_configured
        suffix = provider if configured else f"{provider} not configured"
        return f"{self.name}: {suffix}{status}"

    def clean(self):
        super().clean()
        if self.is_active:
            validate_email(self.from_email)

    def validate_activation(self):
        if not self.is_active:
            return
        if self.provider == self.Provider.SES:
            from apps.core.models import AWSCredentialConfig

            if not AWSCredentialConfig.load().ses_configured:
                raise ValidationError({"provider": "Active AWS SES credentials are required before activation."})
        elif self.provider == self.Provider.SMTP and not SMTPProviderConfig.load().is_configured:
            raise ValidationError({"provider": "An active SMTP configuration is required before activation."})

    def save(self, *args, **kwargs):
        if self.is_active:
            with transaction.atomic():
                list(EmailServiceConfig.objects.select_for_update().filter(is_active=True).exclude(pk=self.pk))
                EmailServiceConfig.objects.filter(is_active=True).exclude(pk=self.pk).update(is_active=False)
                super().save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        """Load the active config.

        Returns an unsaved instance with defaults when no active row exists so that
        callers can safely access properties like ``ses_configured`` without
        guarding against ``None``. Inactive sender settings are never used as a
        fallback.
        """
        try:
            return cls.objects.get(is_active=True)
        except cls.DoesNotExist:
            return cls()

    @property
    def source_address(self):
        """Formatted sender address for email headers."""
        if self.from_name:
            return f"{self.from_name} <{self.from_email}>"
        return self.from_email

    @property
    def ses_configured(self):
        """SES requires both an active sender row and active AWS credentials."""
        from apps.core.models import AWSCredentialConfig

        return bool(
            self.pk
            and self.is_active
            and self.provider == self.Provider.SES
            and self.from_email
            and AWSCredentialConfig.load().ses_configured
        )

    @property
    def delivery_configured(self):
        """Return whether the selected provider is structurally ready."""
        if not (self.pk and self.is_active and self.from_email):
            return False
        try:
            validate_email(self.from_email)
        except ValidationError:
            return False
        if self.provider == self.Provider.SES:
            return self.ses_configured
        if self.provider == self.Provider.SMTP:
            return SMTPProviderConfig.load().is_configured
        return False


class SMTPProviderConfig(ProjectControlModel):
    """Credentials and connection settings for an SMTP email provider."""

    name = models.CharField(max_length=128, default="Default", verbose_name="Config Name")
    is_active = models.BooleanField(
        default=False,
        verbose_name="Active",
        help_text="Only one SMTP provider config can be active. Activating this will deactivate others.",
    )
    host = models.CharField(max_length=254, verbose_name="SMTP Host")
    port = models.PositiveIntegerField(default=587, verbose_name="SMTP Port")
    use_tls = models.BooleanField(default=True, verbose_name="Use TLS")
    use_ssl = models.BooleanField(default=False, verbose_name="Use SSL")
    username = models.CharField(max_length=254, blank=True, default="", verbose_name="SMTP Username")
    password = models.CharField(max_length=256, blank=True, default="", verbose_name="SMTP Password")
    timeout = models.PositiveIntegerField(default=30, verbose_name="Connection Timeout (seconds)")

    class Meta:
        verbose_name = "SMTP Provider Config"
        verbose_name_plural = "SMTP Provider Configs"
        constraints = [
            models.UniqueConstraint(
                fields=["is_active"],
                condition=models.Q(is_active=True),
                name="core_one_active_smtp_provider_config",
            ),
        ]

    def __str__(self):
        status = " (active)" if self.is_active else ""
        endpoint = f"{self.host}:{self.port}" if self.host else "not configured"
        return f"{self.name}: {endpoint}{status}"

    def clean(self):
        super().clean()
        errors = {}
        if self.use_tls and self.use_ssl:
            errors["use_ssl"] = "TLS and SSL cannot both be enabled."
        if bool(self.username) != bool(self.password):
            message = "SMTP username and password must be provided together."
            errors["username" if self.password else "password"] = message
        if not 1 <= self.port <= 65535:
            errors["port"] = "SMTP port must be between 1 and 65535."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean(validate_constraints=False)
        if self.is_active:
            with transaction.atomic():
                list(type(self).objects.select_for_update().filter(is_active=True).exclude(pk=self.pk))
                type(self).objects.filter(is_active=True).exclude(pk=self.pk).update(is_active=False)
                super().save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        """Return the active SMTP provider, or an unsaved instance with defaults."""
        try:
            return cls.objects.get(is_active=True)
        except cls.DoesNotExist:
            return cls()

    @property
    def is_configured(self):
        return bool(not self._state.adding and self.is_active and self.host and (not self.username or self.password))
