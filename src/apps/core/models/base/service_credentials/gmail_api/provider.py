"""The Gmail API provider configuration: its fields, how it is saved, and which row is active."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction

from ...abstract.control import ProjectControlModel
from .limits import default_max_message_bytes, default_max_recipients
from .provider_status import GmailApiProviderStatusMixin

ACTIVE_NEEDS_KEY = "Install the service-account key before activating this configuration."
TAKEOVER_REFUSED = (
    "Mail → Notification Delivery sends email through the Gmail API, so this configuration can become the active "
    "one only when email could switch to it: {problem}"
)
# The ceilings themselves are GMAIL_API settings (a deployment may override them); the admin form names the values.
RECIPIENTS_HELP = "Recipients one message may have (To and Cc)."
MESSAGE_BYTES_HELP = "Size of the encoded message."
CEILING_HELP = "At most Google's documented limit; it can be lowered here, not raised."


class GmailApiProviderConfig(GmailApiProviderStatusMixin, ProjectControlModel):
    """A Google service account with domain-wide delegation for ``gmail.send``, used to send email as Workspace users.

    The site impersonates only the accounts on the subject allow-list (``GmailApiSubject``), and always sends From
    the impersonated account. The service-account key lives in the credential store (AWS Secrets Manager in
    production); this row keeps only a pointer to the pinned stored version and the key's public facts. Keys are
    installed and removed on their own admin pages, by staff granted the Core app.
    """

    class CredentialMail(models.TextChoices):
        SEND = "send", "Send (Gmail keeps a copy in Sent)"
        REFUSE = "refuse", "Refuse (send it through another provider)"

    name = models.CharField(max_length=128, default="Default", verbose_name="Config Name")
    is_active = models.BooleanField(
        default=False,
        verbose_name="Active",
        help_text="Only one Gmail API config can be active. Activating this will deactivate others.",
    )
    key_secret_ref = models.CharField(max_length=512, blank=True, default="", verbose_name="Key Store Reference")
    key_version_id = models.CharField(max_length=64, blank=True, default="", verbose_name="Key Store Version")
    service_account_email = models.CharField(max_length=254, blank=True, default="", verbose_name="Service Account")
    client_id = models.CharField(
        max_length=32,
        blank=True,
        default="",
        verbose_name="Client ID",
        help_text="The numeric client ID the Workspace super admin authorizes for domain-wide delegation.",
    )
    key_id = models.CharField(max_length=64, blank=True, default="", verbose_name="Key ID")
    project_id = models.CharField(max_length=64, blank=True, default="", verbose_name="Google Cloud Project")
    key_installed_at = models.DateTimeField(null=True, blank=True, verbose_name="Key Installed")
    access_checked_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Access Check Passed",
        help_text="When the access check last passed for the installed key (every check, the scope breadth included).",
    )
    max_recipients_per_message = models.PositiveIntegerField(
        default=default_max_recipients,
        verbose_name="Max Recipients per Message",
        help_text=f"{RECIPIENTS_HELP} {CEILING_HELP}",
    )
    max_message_bytes = models.PositiveIntegerField(
        default=default_max_message_bytes,
        verbose_name="Max Message Size (bytes)",
        help_text=f"{MESSAGE_BYTES_HELP} {CEILING_HELP}",
    )
    credential_mail = models.CharField(
        max_length=8,
        choices=CredentialMail.choices,
        default=CredentialMail.SEND,
        verbose_name="Mail With Codes or Login Links",
        help_text=(
            "Gmail always keeps a copy of what it sends in the account's Sent folder. Refuse makes sign-in codes, "
            "login links, invitations and tickets fail with this provider instead."
        ),
    )

    class Meta:
        verbose_name = "Gmail API Provider Config"
        verbose_name_plural = "Gmail API Provider Configs"
        constraints = [
            models.UniqueConstraint(
                fields=["is_active"], condition=models.Q(is_active=True), name="core_one_active_gmail_api_config"
            ),
        ]

    def __str__(self):
        status = " (active)" if self.is_active else ""
        return f"{self.name}: {self.service_account_email or 'no key installed'}{status}"

    def clean(self):
        super().clean()
        errors = {}
        if self.is_active and not self.key_configured:
            errors["is_active"] = ACTIVE_NEEDS_KEY
        ceilings = (
            ("max_recipients_per_message", settings.GMAIL_API["max_recipients_per_message"]),
            ("max_message_bytes", settings.GMAIL_API["max_message_bytes"]),
        )
        for field, ceiling in ceilings:
            value = getattr(self, field)
            if isinstance(value, int) and not 1 <= value <= ceiling:
                errors[field] = f"Must be between 1 and {ceiling:,} (the documented limit)."
        problem = self._takeover_problem()
        if problem:
            errors.setdefault("is_active", TAKEOVER_REFUSED.format(problem=problem))
        if errors:
            raise ValidationError(errors)

    def _takeover_problem(self) -> str:
        """While email is sent through the Gmail API, activating another config moves email to it: it needs what
        switching email to the Gmail API needs (``activation_problem``)."""
        if not self.is_active or self._state.adding:
            return ""
        from ..email import EmailServiceConfig  # email imports this package

        email = EmailServiceConfig.objects.filter(is_active=True, provider=EmailServiceConfig.Provider.GMAIL).first()
        if email is None or type(self).objects.filter(pk=self.pk, is_active=True).exists():
            return ""
        return self.activation_problem(email.from_email)

    def validate_constraints(self, exclude=None):
        # save() replaces the active row atomically; the database still enforces uniqueness.
        exclude = set(exclude or ())
        if self.is_active:
            exclude.add("is_active")
        super().validate_constraints(exclude=exclude)

    def save(self, *args, **kwargs):
        self.full_clean(validate_constraints=False)
        if self.is_active:
            with transaction.atomic():
                list(type(self).objects.select_for_update().filter(is_active=True).exclude(pk=self.pk))
                type(self).objects.filter(is_active=True).exclude(pk=self.pk).update(is_active=False)
                super().save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        """Return the active Gmail API provider, or an unsaved instance with defaults."""
        try:
            return cls.objects.get(is_active=True)
        except cls.DoesNotExist:
            return cls()
