"""A ticket's messages (customer mail, automated mail, internal notes) and their attachments.

Bodies are stored in PostgreSQL: the text as received (scrubbed of personal sign-in links) and the HTML sanitized on
the way in, shown only inside a sandboxed iframe. The raw MIME is never kept: the mailbox still holds the original.
Attachments are stored in the database too (``content``), except blocked file types, files over the size cap, and
anything of a message cut off at the read limit, which keep only their metadata and the reason.
"""

from django.conf import settings
from django.db import models

from apps.core.models import ProjectControlModel

from .ticket import Ticket


class TicketMessage(ProjectControlModel):
    class Kind(models.TextChoices):
        CUSTOMER = "customer", "Customer message"
        AUTOMATED = "automated", "Automated message"
        NOTE = "note", "Internal note"

    INBOUND_KINDS = (Kind.CUSTOMER, Kind.AUTOMATED)

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="messages")
    kind = models.CharField(max_length=12, choices=Kind.choices, db_index=True)
    inbound = models.ForeignKey(
        "core.InboundMessage", null=True, blank=True, on_delete=models.SET_NULL, related_name="helpdesk_messages"
    )
    internet_message_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    in_reply_to = models.CharField(max_length=255, blank=True, default="")
    references = models.JSONField(default=list, blank=True)
    conversation_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    fingerprint = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        help_text="SHA-256 of the Message-ID (or of sender, date, subject and text without one): one copy per message.",
    )
    from_address = models.CharField(max_length=254, blank=True, default="")
    from_name = models.CharField(max_length=255, blank=True, default="")
    to_addresses = models.JSONField(default=list, blank=True)
    cc_addresses = models.JSONField(default=list, blank=True)
    reply_to = models.CharField(max_length=254, blank=True, default="")
    subject = models.CharField(max_length=255, blank=True, default="")
    occurred_at = models.DateTimeField(
        db_index=True, help_text="When the mailbox received it (notes: when written); the Date header is not trusted."
    )
    sent_at = models.DateTimeField(null=True, blank=True, help_text="The message's own Date header, as claimed.")
    body_text = models.TextField(blank=True, default="")
    body_html = models.TextField(blank=True, default="", help_text="Sanitized on the way in.")
    body_truncated = models.BooleanField(default=False)
    body_purged_at = models.DateTimeField(null=True, blank=True)
    attached_messages = models.JSONField(
        default=list, blank=True, help_text="Forwarded or returned messages inside this one (headers, scrubbed text)."
    )
    auth_summary = models.JSONField(default=dict, blank=True, help_text="SPF / DKIM / DMARC results and the SCL.")
    scam_level = models.CharField(max_length=8, blank=True, default="")
    classification = models.CharField(max_length=16, blank=True, default="")
    subtype = models.CharField(max_length=32, blank=True, default="")
    signals = models.JSONField(default=list, blank=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="helpdesk_notes"
    )

    class Meta:
        ordering = ["occurred_at", "created_at"]
        verbose_name = "Ticket Message"
        verbose_name_plural = "Ticket Messages"

    def __str__(self):
        return f"{self.get_kind_display()} on {self.ticket_id}"


class TicketAttachment(ProjectControlModel):
    message = models.ForeignKey(TicketMessage, on_delete=models.CASCADE, related_name="attachments")
    filename = models.CharField(max_length=255)
    declared_type = models.CharField(max_length=127, blank=True, default="")
    detected_type = models.CharField(max_length=127, blank=True, default="", help_text="Sniffed from the content.")
    size = models.PositiveBigIntegerField(default=0)
    sha256 = models.CharField(max_length=64, blank=True, default="")
    is_inline = models.BooleanField(default=False)
    content_id = models.CharField(max_length=255, blank=True, default="")
    blocked = models.BooleanField(default=False, help_text="A dangerous file type: only its metadata is kept.")
    not_stored_reason = models.CharField(max_length=255, blank=True, default="")
    content = models.BinaryField(null=True, blank=True, editable=False)
    purged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Ticket Attachment"
        verbose_name_plural = "Ticket Attachments"

    def __str__(self):
        return self.filename

    @property
    def stored(self) -> bool:
        return self.content is not None
