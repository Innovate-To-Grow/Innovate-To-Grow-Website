"""Email delivery configuration: which provider sends, from which address, and which row is active."""

from django.core.validators import validate_email
from django.db import models, transaction

from .activation import EmailActivationMixin
from .delivery_status import EmailDeliveryStatusMixin


class EmailServiceConfig(EmailActivationMixin, EmailDeliveryStatusMixin, models.Model):
    """
    Email delivery configuration.

    AWS SES credentials and region live on ``AWSCredentialConfig``; this model
    stores email-specific settings like the sender address (send rates live in
    ``DeliveryRatePolicy``). Multiple configs can exist but only one may be active at a
    time.
    """

    class Provider(models.TextChoices):
        SES = "ses", "AWS SES"
        SMTP = "smtp", "SMTP"
        GRAPH = "graph", "Microsoft Graph"
        GMAIL = "gmail", "Gmail API (Google Workspace)"

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

    # Replaced by Mail → Delivery Rates (``DeliveryRatePolicy``), which migration 0036 seeded from it. Kept, not
    # editable, for one release so a task of the previous release still finds the column during a rolling deploy.
    max_send_rate = models.PositiveIntegerField(
        default=10,
        editable=False,
        verbose_name="Campaign Send Rate (emails/sec)",
        help_text="No longer used: rates are set under Mail → Delivery Rates.",
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
