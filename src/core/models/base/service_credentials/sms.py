from django.db import models

from core.services.aws.credentials import aws_credentials_available


class SMSServiceConfig(models.Model):
    """
    AWS SNS SMS verification configuration.

    Uses shared AWS IAM credentials (AWSCredentialConfig or EmailServiceConfig SES keys)
    for authentication. Multiple configs can exist but only one may be active at a time.
    Managed via Django admin under Site Settings.
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

    sns_region = models.CharField(
        max_length=32,
        blank=True,
        default="",
        verbose_name="SNS Region",
        help_text="AWS region for SNS SMS. Leave blank to use the shared AWS credential region.",
    )
    from_number = models.CharField(
        max_length=20,
        blank=True,
        default="",
        verbose_name="Origination Phone Number",
        help_text="SNS-registered origination number in E.164 format (e.g. +12065551234).",
    )
    message_template = models.CharField(
        max_length=320,
        blank=True,
        default="",
        verbose_name="OTP Message Template",
        help_text="SMS body template. Must include {code}. Leave blank for the default message.",
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "SMS Service Config"
        verbose_name_plural = "SMS Service Configs"

    def __str__(self):
        status = " (active)" if self.is_active else ""
        if self.is_configured:
            region = self.effective_region or "unknown"
            return f"{self.name}: AWS SNS ({region}){status}"
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
    def effective_region(self) -> str:
        if self.sns_region:
            return self.sns_region
        if aws_credentials_available():
            from core.services.aws.credentials import resolve_aws_credentials

            return resolve_aws_credentials().region
        return ""

    @property
    def is_configured(self):
        return bool(self.from_number and aws_credentials_available())

    def render_otp_message(self, code: str) -> str:
        template = self.message_template.strip() or (
            "Your Innovate to Grow verification code is {code}. It expires in 10 minutes."
        )
        if "{code}" not in template:
            raise ValueError("OTP message template must include {code}.")
        return template.format(code=code)
