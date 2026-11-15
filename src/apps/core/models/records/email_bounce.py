"""Bounce notifications read from the sending mailbox, and the bounce processor's durable state.

``EmailBounce`` holds one row per failed (or delayed) recipient of one non-delivery report, matched to the outgoing
email it reports on when a reliable identifier allows it (``apps.core.services.email.bounces``). Only the fields
below are kept: never the report's text or the original message's body.

Each row has a fine **category** (what went wrong, from the SMTP reply code, the enhanced status code and, for generic
codes only, the diagnostic text) and the coarse **classification** derived from it (hard, soft, rejected, delayed,
unknown), which the dashboard's charts and an email's worst bounce use.
"""

from django.db import models

from ..base import ProjectControlModel
from .email_telemetry import OutboundEmail

# What each category means for the address and what staff should look at (the bounce lists show it). Only "hard" and
# "mailbox_disabled" are evidence against the address; the rejections point at our own sending.
CATEGORY_GUIDANCE = {
    "hard": "The address does not exist. Strong evidence: mark it undeliverable or replace it.",
    "mailbox_disabled": "The mailbox is disabled. Strong evidence: replace the address, or mark it undeliverable.",
    "mailbox_full": "The mailbox is full: temporary. It only counts toward the repeated-failure threshold.",
    "transient": (
        "Temporary problem (connection, DNS, timeout, expired after retries, message size): the address is probably "
        "fine. It only counts toward the repeated-failure threshold; the next campaign tries it again."
    ),
    "spam_rejected": (
        "Our sending side: spam filtering, a block list, our sending reputation or sender authentication (SPF, DKIM, "
        "DMARC), or the content. Check those, not the contact."
    ),
    "relay_denied": (
        "Our sending side: the receiving server refused to relay our message. Check our sending route and "
        "authorisation (connector, sending mailbox, SPF), not the contact."
    ),
    "policy_rejected": (
        "The recipient's server policy refused the message (for example a group that only takes internal senders). "
        "Not a bad address: no action on the contact."
    ),
    "delayed": "Still retrying: not a failure yet.",
    "unknown": (
        "Unclear: the report gives no specific code or reason. It only counts toward the repeated-failure threshold; "
        "read the diagnostic."
    ),
}
# The same in a few words, for table rows.
CATEGORY_HINTS = {
    "hard": "Evidence against the address",
    "mailbox_disabled": "Evidence against the address",
    "mailbox_full": "Temporary: counts toward the threshold only",
    "transient": "Temporary: the address is probably fine",
    "spam_rejected": "Our sending side: reputation, authentication or content",
    "relay_denied": "Our sending side: sending route or authorisation",
    "policy_rejected": "The recipient's policy: no action on the contact",
    "delayed": "Still retrying",
    "unknown": "Unclear: counts toward the threshold only",
}


class EmailBounce(ProjectControlModel):
    class Classification(models.TextChoices):
        HARD = "hard", "Hard bounce"
        SOFT = "soft", "Soft bounce"
        REJECTED = "rejected", "Rejected"
        DELAYED = "delayed", "Delivery delayed"
        UNKNOWN = "unknown", "Unknown delivery status"

    class Category(models.TextChoices):
        HARD = "hard", "Address does not exist"
        MAILBOX_DISABLED = "mailbox_disabled", "Mailbox disabled"
        MAILBOX_FULL = "mailbox_full", "Mailbox full"
        TRANSIENT = "transient", "Temporary failure"
        SPAM_REJECTED = "spam_rejected", "Spam or reputation rejection"
        RELAY_DENIED = "relay_denied", "Relay denied"
        POLICY_REJECTED = "policy_rejected", "Recipient policy rejection"
        DELAYED = "delayed", "Delayed (still retrying)"
        UNKNOWN = "unknown", "Unknown failure"

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
    # Database defaults too: the release before categories may still be saving reports while a deploy rolls out.
    smtp_code = models.CharField(
        max_length=3,
        blank=True,
        default="",
        db_default="",
        help_text="The SMTP reply code (such as 550) of the diagnostic.",
    )
    diagnostic_code = models.CharField(max_length=1000, blank=True, default="")
    reporting_mta = models.CharField(max_length=255, blank=True, default="")
    remote_mta = models.CharField(max_length=255, blank=True, default="")
    classification = models.CharField(max_length=16, choices=Classification.choices, db_index=True)
    category = models.CharField(
        max_length=24,
        choices=Category.choices,
        blank=True,
        default="",
        db_default="",
        db_index=True,
        help_text="What went wrong, from the SMTP reply code, the enhanced status code and (for generic codes only) "
        "the diagnostic text; the classification is derived from it. Empty: not classified yet (a report saved by "
        "the previous release during a deploy), classified when the bounced addresses are next counted.",
    )
    is_permanent = models.BooleanField(
        null=True,
        blank=True,
        help_text="Whether the address itself will not work (address does not exist, mailbox disabled); empty when "
        "the report does not say.",
    )
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
        label = self.get_category_display() or self.get_classification_display() or "Bounce report"
        return f"{label}: {self.recipient or 'unknown recipient'}"

    @property
    def category_hint(self) -> str:
        return self.hint_for(self.category)

    @staticmethod
    def hint_for(category: str) -> str:
        """``guidance_for`` in a few words ("" for an unknown value)."""
        return CATEGORY_HINTS.get(category, "")

    @classmethod
    def category_legend(cls) -> list[dict]:
        """Every category with its label and guidance, in order (the bounce lists' legend)."""
        return [
            {"value": value, "label": label, "guidance": cls.guidance_for(value)}
            for value, label in cls.Category.choices
        ]

    @staticmethod
    def guidance_for(category: str) -> str:
        """What a category means for the address and what to look at ("" for an unknown value)."""
        return CATEGORY_GUIDANCE.get(category, "")


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
