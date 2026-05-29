from django.db import models


class AWSCredentialConfig(models.Model):
    """
    Unified AWS configuration.

    Stores the IAM access key, AWS region, and the SNS SMS origination
    phone number used by SES (email), SNS (SMS phone verification), and
    Bedrock (System Intelligence). All three services share the same
    region. Multiple configs can exist but only one may be active at a
    time. Managed via Django admin under Site Settings.
    """

    name = models.CharField(
        max_length=128,
        default="Default",
        verbose_name="Config Name",
        help_text="A label to identify this configuration (e.g. 'Production IAM', 'Dev Account').",
    )
    is_active = models.BooleanField(
        default=False,
        verbose_name="Active",
        help_text="Only one config can be active. Activating this will deactivate others.",
    )

    access_key_id = models.CharField(
        max_length=128,
        blank=True,
        default="",
        verbose_name="Access Key ID",
        help_text="AWS IAM access key ID (starts with AKIA…). Shared by SES, SNS, and Bedrock.",
    )
    secret_access_key = models.CharField(
        max_length=256,
        blank=True,
        default="",
        verbose_name="Secret Access Key",
    )
    default_region = models.CharField(
        max_length=32,
        blank=True,
        default="us-west-2",
        verbose_name="AWS Region",
        help_text="AWS region used by SES, SNS, and Bedrock.",
    )
    sms_from_number = models.CharField(
        max_length=20,
        blank=True,
        default="",
        verbose_name="SMS Origination Number",
        help_text="SNS-registered origination number in E.164 format (e.g. +12065551234).",
    )
    sms_message_template = models.CharField(
        max_length=320,
        blank=True,
        default="",
        verbose_name="SMS OTP Message Template",
        help_text="SMS body template. Must include {code}. Leave blank for the default message.",
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "AWS Credential Config"
        verbose_name_plural = "AWS Credential Configs"

    def __str__(self):
        status = " (active)" if self.is_active else ""
        key_hint = f"...{self.access_key_id[-4:]}" if self.access_key_id else "empty"
        return f"{self.name}: {key_hint}{status}"

    def save(self, *args, **kwargs):
        if self.is_active:
            AWSCredentialConfig.objects.filter(is_active=True).exclude(pk=self.pk).update(is_active=False)
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
    def region(self) -> str:
        return self.default_region or "us-west-2"

    @property
    def is_configured(self) -> bool:
        return bool(self.access_key_id and self.secret_access_key)

    @property
    def ses_configured(self) -> bool:
        return self.is_configured

    @property
    def sns_configured(self) -> bool:
        return self.is_configured and bool(self.sms_from_number)

    def render_sms_otp_message(self, code: str) -> str:
        template = self.sms_message_template.strip() or (
            "Your Innovate to Grow verification code is {code}. It expires in 10 minutes."
        )
        if "{code}" not in template:
            raise ValueError("SMS OTP message template must include {code}.")
        return template.format(code=code)
