from django.db import models


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
