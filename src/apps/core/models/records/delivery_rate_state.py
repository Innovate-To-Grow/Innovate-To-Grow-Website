from django.db import models

from ..base import ProjectControlModel
from ..base.delivery_rates import DeliveryChannel


class DeliveryRateState(ProjectControlModel):
    """Live pacing state of one channel identity: a sender mailbox, an SES account and Region, an SMTP login, an
    SMS origination number, ... (``DeliveryRatePolicy`` holds what people set for the whole channel).

    Only the delivery-rate limiter writes it, in short transactions that never span a provider call. A new identity
    gets a fresh row of its own.
    """

    class Mode(models.TextChoices):
        SMART = "smart", "Smart rate"
        MANUAL = "manual", "Manual rate"

    class BreakerState(models.TextChoices):
        CLOSED = "closed", "Closed"
        OPEN = "open", "Open"
        HALF_OPEN = "half_open", "Half-open (probing)"

    class BreakerScope(models.TextChoices):
        ALL = "all", "All mail"
        BULK = "bulk", "Campaigns only"

    channel = models.CharField(max_length=32, choices=DeliveryChannel.choices)
    identity = models.CharField(max_length=512)
    # Rows that share a provider allowance (Outlook: per app and mailbox, both Graph channels) share cooldowns.
    cooldown_group = models.CharField(max_length=512, db_index=True)
    # The mode the last admission ran in; a change is how a Smart rate switch is noticed.
    mode = models.CharField(max_length=16, choices=Mode.choices, blank=True, default="")

    # Pacing: theoretical arrival times of the whole channel and of its bulk lane.
    tat = models.DateTimeField(null=True, blank=True)
    tat_bulk = models.DateTimeField(null=True, blank=True)
    # Hints that let the worker skip jobs that would only be deferred again.
    bulk_gate_until = models.DateTimeField(null=True, blank=True)
    all_gate_until = models.DateTimeField(null=True, blank=True)

    # Smart rate: the factor applied to the bound, when it last changed, and when it was last cut.
    factor_base = models.FloatField(default=1.0)
    factor_changed_at = models.DateTimeField(null=True, blank=True)
    last_cut_at = models.DateTimeField(null=True, blank=True)

    # Cooldown the provider asked for (Retry-After) or a backoff after a throttle.
    cooldown_until = models.DateTimeField(null=True, blank=True)
    cooldown_reason = models.CharField(max_length=64, blank=True, default="")
    consecutive_throttles = models.PositiveIntegerField(default=0)

    # Breaker: stops the channel (or only its campaigns) until a timed probe or a provider report shows it is clear.
    breaker_state = models.CharField(max_length=16, choices=BreakerState.choices, default=BreakerState.CLOSED)
    breaker_scope = models.CharField(max_length=16, choices=BreakerScope.choices, blank=True, default="")
    breaker_reason = models.CharField(max_length=64, blank=True, default="")
    breaker_retry_at = models.DateTimeField(null=True, blank=True)
    breaker_interval_seconds = models.PositiveIntegerField(null=True, blank=True)
    # Identifies the one request let through as the probe (compare-and-set), not a credential.
    breaker_probe_id = models.UUIDField(null=True, blank=True)
    breaker_probe_started_at = models.DateTimeField(null=True, blank=True)

    # Last successful provider limit read (kept when a later read fails) and the next one due.
    discovered_rate = models.FloatField(null=True, blank=True)
    discovered_parts_rate = models.FloatField(null=True, blank=True)
    discovered_daily = models.PositiveBigIntegerField(null=True, blank=True)
    discovered_used_24h = models.PositiveBigIntegerField(null=True, blank=True)
    discovered_extra = models.JSONField(default=dict, blank=True)
    discovered_at = models.DateTimeField(null=True, blank=True)
    discovery_next_at = models.DateTimeField(null=True, blank=True)
    discovery_error = models.CharField(max_length=255, blank=True, default="")

    # Diagnostics for the admin status line.
    last_signal = models.CharField(max_length=32, blank=True, default="")
    last_signal_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Delivery Rate State"
        verbose_name_plural = "Delivery Rate States"
        ordering = ("channel", "identity")
        constraints = [
            models.UniqueConstraint(fields=["channel", "identity"], name="core_unique_delivery_rate_state"),
        ]

    def __str__(self):
        return f"{self.channel}:{self.identity}"


class DeliveryUsageBucket(ProjectControlModel):
    """What one channel identity sent in one fixed time bucket, for the rolling daily and hourly limits.

    ``total`` is in budget units (recipients; SMS: messages), and ``bulk`` and ``external`` are the parts of it sent
    by campaigns and to external recipients.
    """

    state = models.ForeignKey(DeliveryRateState, on_delete=models.CASCADE, related_name="usage_buckets")
    bucket_start = models.DateTimeField(db_index=True)
    total = models.PositiveIntegerField(default=0)
    bulk = models.PositiveIntegerField(default=0)
    external = models.PositiveIntegerField(default=0)
    messages = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Delivery Usage Bucket"
        verbose_name_plural = "Delivery Usage Buckets"
        ordering = ("state", "bucket_start")
        constraints = [
            models.UniqueConstraint(fields=["state", "bucket_start"], name="core_unique_delivery_usage_bucket"),
        ]

    def __str__(self):
        return f"{self.state}@{self.bucket_start.isoformat()}: {self.total}"
