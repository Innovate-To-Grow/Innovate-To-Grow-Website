"""The Workspace users the Gmail API provider may send as."""

from django.core.exceptions import ValidationError
from django.db import models

from apps.core.utils.security import is_plain_address

from ...control import ProjectControlModel

SUBJECT_FORMAT = "Enter the primary address of a Google Workspace user: plain ASCII, no '+' tag, no display name."


def normalize_subject(value) -> str:
    """Google account addresses compare case-insensitively."""
    return str(value or "").strip().lower()


def is_subject(value) -> bool:
    """A plain ASCII address with no ``+`` tag: the form of a Workspace user's primary address."""
    text = str(value or "")
    return text.isascii() and "+" not in text and len(text) <= 254 and is_plain_address(text)


class GmailApiSubject(ProjectControlModel):
    """One Google account the site may impersonate (and send From). Google cannot restrict domain-wide delegation
    per user, so this list is the only per-user control: it guards against site errors, not against a key holder."""

    config = models.ForeignKey("core.GmailApiProviderConfig", on_delete=models.CASCADE, related_name="subjects")
    subject = models.CharField(
        max_length=254,
        verbose_name="Google Account",
        help_text="The primary address of a Workspace user the site may send as.",
    )
    verified_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Verified",
        help_text="When the access check last obtained a gmail.send token for this account with the installed key.",
    )

    class Meta:
        verbose_name = "Gmail API Account"
        verbose_name_plural = "Gmail API Accounts (allow-list)"
        ordering = ("subject",)
        constraints = [
            models.UniqueConstraint(fields=["config", "subject"], name="core_unique_gmail_api_subject"),
        ]

    def __str__(self):
        return self.subject

    def clean(self):
        super().clean()
        self.subject = normalize_subject(self.subject)
        if not is_subject(self.subject):
            raise ValidationError({"subject": SUBJECT_FORMAT})

    def save(self, *args, **kwargs):
        self.subject = normalize_subject(self.subject)
        if not self._state.adding:
            stored = type(self).objects.filter(pk=self.pk).values_list("subject", flat=True).first()
            if stored is not None and stored != self.subject:
                self.verified_at = None  # a token test proves only the account it was made for
        super().save(*args, **kwargs)
