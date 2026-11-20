"""What the universal inbox last learned about each mailbox it reads, shared by every web and worker container.

Production has no shared cache (each container keeps its own file cache), so the inbox poller
(``apps.mail.services.inbox.polling.poller``) records here whether each account could be read and the newest messages of
its Inbox. The admin inbox lists from this snapshot while it is fresh, hides accounts that could not be reached, and
the sidebar shows the unread count, all without connecting to a mailbox.
"""

from django.db import models

from apps.core.models import ProjectControlModel


class InboxAccountState(ProjectControlModel):
    """One inbox account (``accounts.InboxAccount.key``): its last connection outcome and Inbox snapshot."""

    class Status(models.TextChoices):
        UNKNOWN = "unknown", "Not checked yet"
        OK = "ok", "Connected"
        BUSY = "busy", "Held back (rate limit)"
        UNREACHABLE = "unreachable", "Could not connect"

    account_key = models.CharField(max_length=300, unique=True)
    address = models.CharField(max_length=254, blank=True, default="")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.UNKNOWN)
    detail = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="What staff may be shown about the last failure (never a raw provider error).",
    )
    checked_at = models.DateTimeField(null=True, blank=True)
    connected_at = models.DateTimeField(null=True, blank=True)
    snapshot_at = models.DateTimeField(null=True, blank=True)
    consecutive_failures = models.PositiveIntegerField(default=0)
    unread_count = models.PositiveIntegerField(default=0)
    messages = models.JSONField(
        default=list,
        blank=True,
        help_text="The newest Inbox message summaries (no bodies), newest first; replaced on every poll.",
    )

    class Meta:
        verbose_name = "Inbox Account State"
        verbose_name_plural = "Inbox Account States"
        ordering = ("account_key",)

    def __str__(self):
        return f"{self.address or self.account_key}: {self.get_status_display()}"
