"""Bounce notifications read from the sending mailbox, and the bounce processor's durable state.

``EmailBounce`` holds one row per failed (or delayed) recipient of one non-delivery report, matched to the outgoing
email it reports on when a reliable identifier allows it (``apps.core.services.email.bounces``). Only the fields
below are kept: never the report's text or the original message's body.
"""

from django.db import models

from ..base import ProjectControlModel
from .email_telemetry import OutboundEmail


class EmailBounce(ProjectControlModel):
    class Classification(models.TextChoices):
        HARD = "hard", "Hard bounce"
        SOFT = "soft", "Soft bounce"
        REJECTED = "rejected", "Rejected"
        DELAYED = "delayed", "Delivery delayed"
        UNKNOWN = "unknown", "Unknown delivery status"

    class MatchMethod(models.TextChoices):
        MESSAGE_ID = "message_id", "Exact: original Message-ID"
        RECIPIENT = "recipient", "Inferred: recipient, subject and time"
        UNMATCHED = "unmatched", "Not matched"

    dedupe_key = models.CharField(max_length=64, unique=True, editable=False)
    mailbox = models.CharField(max_length=254)
    ndr_graph_id = models.CharField(max_length=512, db_index=True)
    ndr_message_id = models.CharField(max_length=255, blank=True, default="")
    received_at = models.DateTimeField(db_index=True, help_text="When the report arrived in the mailbox.")
    bounced_at = models.DateTimeField(null=True, blank=True, help_text="The report's own date, when it gives one.")
    recipient = models.CharField(max_length=254, blank=True, default="", db_index=True)
    original_message_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    original_subject = models.CharField(max_length=255, blank=True, default="")
    action = models.CharField(max_length=16, blank=True, default="")
    status_code = models.CharField(max_length=16, blank=True, default="")
    diagnostic_code = models.CharField(max_length=1000, blank=True, default="")
    reporting_mta = models.CharField(max_length=255, blank=True, default="")
    remote_mta = models.CharField(max_length=255, blank=True, default="")
    classification = models.CharField(max_length=16, choices=Classification.choices, db_index=True)
    is_permanent = models.BooleanField(null=True, blank=True)
    reason = models.CharField(max_length=255, blank=True, default="")
    email = models.ForeignKey(OutboundEmail, null=True, blank=True, on_delete=models.SET_NULL, related_name="bounces")
    campaign_id = models.UUIDField(null=True, blank=True, db_index=True)
    match_method = models.CharField(
        max_length=16, choices=MatchMethod.choices, default=MatchMethod.UNMATCHED, db_index=True
    )
    match_note = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["-received_at"]
        verbose_name = "Email Bounce"
        verbose_name_plural = "Email Bounces"

    def __str__(self):
        return f"{self.get_classification_display()}: {self.recipient or 'unknown recipient'}"


class EmailMonitorState(ProjectControlModel):
    """The bounce processor's checkpoint, lease and health for one mailbox (shown on the monitoring dashboard)."""

    mailbox = models.CharField(max_length=254, unique=True)
    paused = models.BooleanField(default=False, help_text="Paused from the dashboard: scans skip this mailbox.")
    checkpoint_at = models.DateTimeField(
        null=True, blank=True, help_text="Received time of the newest message every scan before it fully processed."
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
