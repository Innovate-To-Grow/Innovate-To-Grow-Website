"""Outgoing email telemetry: one row per logical email and one per provider attempt.

Written only by the email delivery facade (``apps.core.services.email.telemetry``) and the Microsoft Graph access
check's probe sends; staff read them on Mail → Delivery Operations → Email Monitoring. Retries of one email (a
background job running again, a campaign recipient sent again after a throttle) share one ``OutboundEmail`` and add
one ``OutboundEmailAttempt`` each. No body, attachment, access token, certificate or credential is ever stored.

``status`` is what the provider's API said. It is never "delivered": Microsoft Graph's ``202 Accepted`` only means
the message was queued, so ``delivery_status`` stays unknown until a bounce notification proves a failure.
"""

import uuid

from django.db import models
from django.utils import timezone

from ..base import ProjectControlModel


class EmailCategory(models.TextChoices):
    CAMPAIGN = "campaign", "Broadcast campaign"
    VERIFICATION = "verification", "Registration & verification"
    SIGN_IN = "sign_in", "Sign-in code"
    PASSWORD = "password", "Password reset & change"
    ACCOUNT = "account", "Account security"
    NOTIFICATION = "notification", "Automated notification"
    INVITATION = "invitation", "Admin invitation"
    EVENT_TICKET = "event_ticket", "Event ticket & schedule"
    INBOX_REPLY = "inbox_reply", "Inbox reply"
    TEST = "test", "Admin test email"
    ACCESS_CHECK = "access_check", "Graph access check probe"
    OTHER = "other", "Other"


class OutboundEmail(ProjectControlModel):
    """One logical outgoing email: everything sent for one message, however many attempts it took."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "API accepted"
        FAILED = "failed", "API failed"
        UNCERTAIN = "uncertain", "API outcome unknown"
        NOT_SENT = "not_sent", "Not sent"

    class DeliveryStatus(models.TextChoices):
        NOT_APPLICABLE = "not_applicable", "Not accepted"
        UNKNOWN = "unknown", "Delivery status unknown"
        DELAYED = "delayed", "Delivery delayed"
        FAILURE_CONFIRMED = "failure_confirmed", "Delivery failure confirmed"

    correlation_id = models.UUIDField(
        unique=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Stable across retries: derived from the retry key when the sender gives one.",
    )
    category = models.CharField(
        max_length=32, choices=EmailCategory.choices, default=EmailCategory.OTHER, db_index=True
    )
    subcategory = models.CharField(max_length=100, blank=True, default="")
    campaign_id = models.UUIDField(null=True, blank=True, db_index=True)
    source_type = models.CharField(max_length=64, blank=True, default="")
    source_id = models.CharField(max_length=64, blank=True, default="")
    job_id = models.UUIDField(null=True, blank=True)
    provider = models.CharField(max_length=16, blank=True, default="", db_index=True)
    mailbox = models.CharField(max_length=254, blank=True, default="")
    recipient = models.CharField(
        max_length=254, blank=True, default="", db_index=True, help_text="The first envelope recipient, lower-case."
    )
    recipients = models.JSONField(default=list, blank=True, help_text="Every envelope recipient (To, Cc, Bcc).")
    recipient_count = models.PositiveIntegerField(default=0)
    subject = models.CharField(max_length=255, blank=True, default="")
    subject_digest = models.CharField(max_length=64, blank=True, default="", db_index=True)
    internet_message_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    send_format = models.CharField(max_length=8, blank=True, default="")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    delivery_status = models.CharField(
        max_length=20, choices=DeliveryStatus.choices, default=DeliveryStatus.NOT_APPLICABLE, db_index=True
    )
    bounce_classification = models.CharField(max_length=16, blank=True, default="")
    attempt_count = models.PositiveSmallIntegerField(default=0)
    deferral_count = models.PositiveIntegerField(default=0)
    first_attempt_at = models.DateTimeField(null=True, blank=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True, db_index=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    bounced_at = models.DateTimeField(null=True, blank=True)
    total_duration_ms = models.PositiveIntegerField(default=0)
    last_http_status = models.PositiveSmallIntegerField(null=True, blank=True)
    last_error_kind = models.CharField(max_length=32, blank=True, default="")
    last_error_code = models.CharField(max_length=64, blank=True, default="")
    last_error = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Outgoing Email"
        verbose_name_plural = "Outgoing Emails"
        indexes = [
            models.Index(fields=["category", "created_at"], name="core_outemail_category_idx"),
            models.Index(fields=["status", "created_at"], name="core_outemail_status_idx"),
            models.Index(fields=["campaign_id", "created_at"], name="core_outemail_campaign_idx"),
            models.Index(fields=["recipient", "last_attempt_at"], name="core_outemail_recipient_idx"),
        ]

    def __str__(self):
        return f"{self.get_category_display()} to {self.recipient or 'no recipient'} [{self.status}]"

    @property
    def retry_count(self) -> int:
        return max(0, self.attempt_count - 1)

    @property
    def bounce_label(self) -> str:
        """The worst bounce classification's label ("Hard bounce", "Rejected", ...), or ""."""
        from .email_bounce import EmailBounce  # that module imports this one

        return dict(EmailBounce.Classification.choices).get(self.bounce_classification, "")


class OutboundEmailAttempt(ProjectControlModel):
    """One provider call for an email (for Microsoft Graph: the token step, if needed, and one ``sendMail``)."""

    class Outcome(models.TextChoices):
        IN_PROGRESS = "in_progress", "In progress"
        ACCEPTED = "accepted", "Accepted"
        TRANSIENT = "transient", "Failed (retryable)"
        PERMANENT = "permanent", "Failed (permanent)"
        UNCERTAIN = "uncertain", "Outcome unknown"
        NOT_SENT = "not_sent", "Stopped before sending"

    class Operation(models.TextChoices):
        COMPOSE = "compose", "Compose message"
        TOKEN = "token", "Access token request"
        SEND_MAIL = "send_mail", "Graph sendMail"
        PROVIDER = "provider", "Provider send"
        PROBE = "probe", "Access check probe"

    email = models.ForeignKey(OutboundEmail, on_delete=models.CASCADE, related_name="attempts")
    attempt_number = models.PositiveSmallIntegerField(default=1)
    provider = models.CharField(max_length=16, blank=True, default="")
    operation = models.CharField(max_length=16, choices=Operation.choices, default=Operation.PROVIDER)
    endpoint = models.CharField(max_length=128, blank=True, default="")
    outcome = models.CharField(max_length=16, choices=Outcome.choices, default=Outcome.IN_PROGRESS, db_index=True)
    error_kind = models.CharField(max_length=32, blank=True, default="", db_index=True)
    http_status = models.PositiveSmallIntegerField(null=True, blank=True)
    error_code = models.CharField(max_length=64, blank=True, default="")
    inner_error_code = models.CharField(max_length=64, blank=True, default="")
    error_message = models.CharField(max_length=500, blank=True, default="")
    request_id = models.CharField(max_length=64, blank=True, default="")
    client_request_id = models.CharField(max_length=64, blank=True, default="")
    retry_after_seconds = models.PositiveIntegerField(null=True, blank=True)
    token_fresh = models.BooleanField(null=True, blank=True)
    started_at = models.DateTimeField(default=timezone.now, db_index=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    response_ms = models.PositiveIntegerField(null=True, blank=True)
    job_attempt = models.PositiveSmallIntegerField(null=True, blank=True)
    diagnostics = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["email", "attempt_number"]
        verbose_name = "Outgoing Email Attempt"
        verbose_name_plural = "Outgoing Email Attempts"
        constraints = [
            models.UniqueConstraint(fields=["email", "attempt_number"], name="core_unique_email_attempt_number"),
        ]
        indexes = [
            models.Index(fields=["started_at", "outcome"], name="core_emailattempt_outcome_idx"),
            models.Index(fields=["http_status", "started_at"], name="core_emailattempt_status_idx"),
        ]

    def __str__(self):
        return f"Attempt {self.attempt_number} ({self.get_outcome_display()})"
