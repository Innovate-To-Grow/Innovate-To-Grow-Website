"""Mailboxes of a Graph configuration: how addresses compare, which may be the access check's deny mailbox, and the
mailboxes a configuration may use, with which permissions."""

from django.core.exceptions import ValidationError
from django.db import models

from apps.core.utils.security import is_exchange_mailbox, is_plain_address

from ...abstract.control import ProjectControlModel

# Characters that would change a Graph URL (percent-encoding keeps them out of the path, but a deny mailbox that
# needs them is never what an operator meant).
_URL_CHARACTERS = frozenset("/?#%\\")


def normalize_mailbox(value: str) -> str:
    """Exchange addresses, UPNs and object IDs compare case-insensitively."""
    return str(value or "").strip().lower()


def is_deny_mailbox(value: str) -> bool:
    """A mailbox the access check may use as its deny mailbox: a plain email address (it is also the From address
    of the probes that must be refused), with nothing that could change a Graph URL."""
    return is_plain_address(value) and not _URL_CHARACTERS & set(value)


class MicrosoftGraphMailboxScope(ProjectControlModel):
    """One mailbox the Graph app may use, with the permission level the site may exercise on it.

    The site refuses any Graph request for a mailbox or permission not listed here. This mirrors, and does not
    replace, the Exchange Online restriction that must limit the Entra app (an Application Access Policy or RBAC
    for Applications, set by OIT); only the access check shows whether Microsoft enforces it.
    """

    class Permission(models.TextChoices):
        SEND = "send", "Send only (Mail.Send)"
        READ = "read", "Read only (Mail.Read)"
        SEND_AND_READ = "send_read", "Send and read (Mail.Send + Mail.Read)"

    config = models.ForeignKey(
        "core.MicrosoftGraphProviderConfig", on_delete=models.CASCADE, related_name="mailbox_scopes"
    )
    mailbox = models.CharField(
        max_length=254,
        verbose_name="Mailbox",
        help_text="Email address / user principal name, or object ID (GUID), of a mailbox the app may use.",
    )
    permission = models.CharField(
        max_length=16,
        choices=Permission.choices,
        default=Permission.SEND,
        verbose_name="Permission Level",
        help_text=(
            "Must match the Exchange restriction (Application Access Policy or RBAC for Applications) that OIT "
            "set for this mailbox."
        ),
    )

    class Meta:
        verbose_name = "Microsoft Graph Mailbox Scope"
        verbose_name_plural = "Microsoft Graph Mailbox Scope"
        ordering = ("mailbox",)
        constraints = [
            models.UniqueConstraint(fields=["config", "mailbox"], name="core_unique_graph_mailbox_scope"),
        ]

    def __str__(self):
        return f"{self.mailbox} ({self.get_permission_display()})"

    def clean(self):
        super().clean()
        self.mailbox = normalize_mailbox(self.mailbox)
        if not is_exchange_mailbox(self.mailbox):
            raise ValidationError(
                {"mailbox": "Enter the mailbox email address / user principal name, or its object ID (GUID)."}
            )

    def save(self, *args, **kwargs):
        self.mailbox = normalize_mailbox(self.mailbox)
        super().save(*args, **kwargs)

    def grants(self, permission: str) -> bool:
        return self.level_grants(self.permission, permission)

    @classmethod
    def level_grants(cls, level, permission: str) -> bool:
        """Whether the permission level *level* (a ``Permission`` value, or None) includes *permission*."""
        if permission == "send":
            return level in (cls.Permission.SEND, cls.Permission.SEND_AND_READ)
        if permission == "read":
            return level in (cls.Permission.READ, cls.Permission.SEND_AND_READ)
        return False
