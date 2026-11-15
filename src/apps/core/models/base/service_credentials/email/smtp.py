"""The SMTP provider configuration."""

from django.core.exceptions import ValidationError
from django.db import models, transaction

from ...abstract.control import ProjectControlModel


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
        if not isinstance(self.port, int) or not 1 <= self.port <= 65535:
            errors["port"] = "SMTP port must be between 1 and 65535."
        if errors:
            raise ValidationError(errors)

    def validate_constraints(self, exclude=None):
        # save() replaces the active row atomically. Do not reject that switch
        # during ModelForm validation; the database still enforces uniqueness.
        exclude = set(exclude or ())
        if self.is_active:
            exclude.add("is_active")
        super().validate_constraints(exclude=exclude)

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
