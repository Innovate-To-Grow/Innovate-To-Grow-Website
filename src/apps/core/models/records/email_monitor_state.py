"""Durable state of the two background readers of delivery evidence: the bounce scan of a sending mailbox
(``EmailMonitorState``) and the optional Microsoft Graph Message Trace sync of a sender (``EmailDeliveryTraceState``).

Each row holds a lease (a conditional update, never a lock held across Microsoft requests), the run's health for the
Email Monitoring dashboard, and when the next run may start. Only their own services write them.
"""

from django.db import models

from ..base import ProjectControlModel


class EmailMonitorState(ProjectControlModel):
    """The bounce processor's checkpoint, lease and health for one mailbox, and the controls staff set for it on the
    monitoring dashboard (pause, first-scan lookback)."""

    mailbox = models.CharField(max_length=254, unique=True)
    paused = models.BooleanField(default=False, help_text="Paused from the dashboard: scans skip this mailbox.")
    checkpoint_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Received time of the newest message every scan before it fully processed, or the earlier time "
        "staff chose with Rescan since.",
    )
    scanned_since = models.DateTimeField(
        null=True,
        blank=True,
        help_text="The earliest received time the scans have read continuously up to the checkpoint: set by the "
        "first scan, moved back by Rescan since. Empty: not known yet, so no email is reported as without bounce.",
    )
    initial_lookback_hours = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="How many hours back the first scan reads while there is no checkpoint (set on the Email Monitoring "
        "dashboard). Empty: the EMAIL_MONITORING default.",
    )
    lease_token = models.UUIDField(null=True, blank=True, editable=False)
    lease_until = models.DateTimeField(null=True, blank=True, editable=False)
    last_run_started_at = models.DateTimeField(null=True, blank=True)
    last_run_finished_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_error_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True, default="")
    consecutive_failures = models.PositiveIntegerField(default=0)
    next_run_after = models.DateTimeField(null=True, blank=True)
    last_run_stats = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Email Monitor State"
        verbose_name_plural = "Email Monitor States"

    def __str__(self):
        return f"Bounce processing for {self.mailbox}"


class EmailDeliveryTraceState(ProjectControlModel):
    """The Message Trace sync's lease, health and backoff for one sender address (off unless the Graph config's
    ``message_trace_enabled`` is set). ``permission`` is what the last run learned of the
    ``ExchangeMessageTrace.Read.All`` application permission."""

    class Permission(models.TextChoices):
        UNKNOWN = "unknown", "Not checked yet"
        OK = "ok", "Granted"
        NOT_PERMITTED = "not_permitted", "Not granted"

    sender = models.CharField(max_length=254, unique=True)
    lease_token = models.UUIDField(null=True, blank=True, editable=False)
    lease_until = models.DateTimeField(null=True, blank=True, editable=False)
    last_run_started_at = models.DateTimeField(null=True, blank=True)
    last_run_finished_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_error_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True, default="")
    consecutive_failures = models.PositiveIntegerField(default=0)
    next_run_after = models.DateTimeField(null=True, blank=True)
    permission = models.CharField(max_length=16, choices=Permission.choices, default=Permission.UNKNOWN)
    last_run_stats = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Email Delivery Trace State"
        verbose_name_plural = "Email Delivery Trace States"

    def __str__(self):
        return f"Message trace sync for {self.sender}"
