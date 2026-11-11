"""The inbound mail queue: one row per message the mailbox scan listed, metadata only.

The bounce processor's scan (``apps.core.services.email.bounces``) records every message it lists in the Microsoft
Graph sending mailbox's Inbox here, once per (mailbox, Graph id), before it handles bounce reports as it always did.
Apps that consume inbound mail register a background job kind with ``apps.core.services.email.inbound`` and drain the
pending rows (the helpdesk turns each into a ticket); ``core`` itself never reads a message body.

Only what the folder listing returns is kept: the subject is cleaned and scrubbed of personal sign-in links and
token-shaped runs, and no body, recipient list or attachment is ever stored here.
"""

from django.db import models

from ..base import ProjectControlModel


class InboundMessage(ProjectControlModel):
    class Folder(models.TextChoices):
        INBOX = "inbox", "Inbox"
        SENT = "sentitems", "Sent Items"

    class Kind(models.TextChoices):
        MESSAGE = "message", "Message"
        BOUNCE_CANDIDATE = "bounce_candidate", "Bounce report candidate"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    mailbox = models.CharField(max_length=254)
    folder = models.CharField(max_length=16, choices=Folder.choices, default=Folder.INBOX)
    graph_id = models.CharField(max_length=512, help_text="Microsoft Graph message id, unique per mailbox.")
    internet_message_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    conversation_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    received_at = models.DateTimeField(db_index=True, help_text="When the message arrived in the mailbox.")
    from_address = models.CharField(max_length=254, blank=True, default="")
    from_name = models.CharField(max_length=255, blank=True, default="")
    subject = models.CharField(max_length=255, blank=True, default="", help_text="Cleaned and token-scrubbed.")
    kind = models.CharField(max_length=24, choices=Kind.choices, default=Kind.MESSAGE)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True, default="")
    classification = models.CharField(max_length=32, blank=True, default="", db_index=True)
    subtype = models.CharField(max_length=32, blank=True, default="")
    result = models.JSONField(
        default=dict, blank=True, help_text='What the consumer made of it, e.g. {"ticket": 1234}.'
    )
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["received_at"]
        verbose_name = "Inbound Message"
        verbose_name_plural = "Inbound Messages"
        constraints = [
            models.UniqueConstraint(fields=["mailbox", "graph_id"], name="core_unique_inbound_graph_id"),
        ]
        indexes = [
            models.Index(fields=["status", "next_attempt_at", "received_at"], name="core_inbound_queue_idx"),
        ]

    def __str__(self):
        return f"{self.from_address or 'unknown sender'}: {self.subject or '(no subject)'}"
