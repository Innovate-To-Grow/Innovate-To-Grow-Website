from django.db import models, transaction


class SendVerificationConfig(models.Model):
    """Site-settings singleton for self-hosted email/SMS send verification.

    HMAC secrets and operational mode live here so they can be rotated and
    paused without a deploy. Environment settings may still override mode and
    numeric policy for tests and cutover.
    """

    class Mode(models.TextChoices):
        OBSERVE = "observe", "Observe (proofs optional)"
        ENFORCE = "enforce", "Enforce (proofs required)"
        PAUSE = "pause", "Pause protected sends"

    name = models.CharField(
        max_length=128,
        default="Default",
        verbose_name="Config Name",
    )
    is_active = models.BooleanField(
        default=False,
        verbose_name="Active",
        help_text="Only one config can be active. Activating this will deactivate others.",
    )
    mode = models.CharField(
        max_length=16,
        choices=Mode.choices,
        default=Mode.OBSERVE,
        help_text="Pause fails closed. Enforce requires a valid proof. Observe logs missing proofs.",
    )
    hmac_secret = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="HMAC secret",
        help_text="Current ALTCHA challenge signing secret. Rotate by moving this value to Previous.",
    )
    hmac_key_secret = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="HMAC key secret",
        help_text="Optional fast-path key-signing secret for PoW v2 deterministic verification.",
    )
    hmac_secret_previous = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Previous HMAC secret",
        help_text="Retained during rotation so in-flight challenges still verify.",
    )
    hmac_key_secret_previous = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Previous HMAC key secret",
    )
    key_version = models.PositiveIntegerField(default=1)
    algorithm = models.CharField(max_length=32, default="PBKDF2/SHA-256")
    cost = models.PositiveIntegerField(
        default=5000,
        help_text="PBKDF2 iteration cost. Clients cannot lower this; it is signed server-side.",
    )
    challenge_ttl_seconds = models.PositiveIntegerField(default=300)
    destination_hourly_limit = models.PositiveIntegerField(default=10)
    destination_cooldown_seconds = models.PositiveIntegerField(default=60)
    sms_daily_limit = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Channel-wide SMS reservation cap per UTC day. Leave empty until calibrated.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Send Verification Config"
        verbose_name_plural = "Send Verification Configs"
        constraints = [
            models.UniqueConstraint(
                fields=["is_active"],
                condition=models.Q(is_active=True),
                name="core_one_active_send_verification_config",
            ),
        ]

    def __str__(self):
        status = " (active)" if self.is_active else ""
        secret = "configured" if self.hmac_secret else "missing secret"
        return f"{self.name}: {self.mode}/{secret}{status}"

    def save(self, *args, **kwargs):
        if self.is_active:
            with transaction.atomic():
                list(SendVerificationConfig.objects.select_for_update().filter(is_active=True).exclude(pk=self.pk))
                SendVerificationConfig.objects.filter(is_active=True).exclude(pk=self.pk).update(is_active=False)
                super().save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        try:
            return cls.objects.get(is_active=True)
        except cls.DoesNotExist:
            return cls()

    @property
    def is_configured(self) -> bool:
        return bool(self.pk and self.is_active and self.hmac_secret)
