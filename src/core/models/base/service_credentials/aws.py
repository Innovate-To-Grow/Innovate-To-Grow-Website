from django.db import models


class AWSCredentialConfig(models.Model):
    """
    General-purpose AWS credential configuration.

    Stores an IAM Access Key that can be shared by multiple AWS services
    (SES, S3, etc.). Multiple configs can exist but only one may be active
    at a time. Managed via Django admin under Site Settings.
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
        help_text="AWS IAM access key ID (starts with AKIA…).",
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
        verbose_name="Default Region",
        help_text="AWS region used when a service does not specify its own.",
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
    def is_configured(self):
        return bool(self.access_key_id and self.secret_access_key)
