import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction

from apps.core.utils.security import is_plain_address

from ..control import ProjectControlModel

# The public facts of an installed service-account key, as Google writes them in the key file.
# client_email: "<account>@<project>.iam.gserviceaccount.com" (account and project ids: 6-30 characters).
SERVICE_ACCOUNT_EMAIL_RE = re.compile(
    r"[a-z][a-z0-9-]{4,28}[a-z0-9]@(?P<project>[a-z][a-z0-9-]{4,28}[a-z0-9])\.iam\.gserviceaccount\.com"
)
PROJECT_ID_RE = re.compile(r"[a-z][a-z0-9-]{4,28}[a-z0-9]")
# The numeric OAuth client id the Workspace admin authorizes for domain-wide delegation.
CLIENT_ID_RE = re.compile(r"[0-9]{1,32}")
# private_key_id: 40 lower-case hex characters in every key file Google documents.
KEY_ID_RE = re.compile(r"[0-9a-f]{40}")
# Secrets Manager VersionId bounds (the credential store's version tokens are UUIDs).
VERSION_ID_RE = re.compile(r"[A-Za-z0-9-]{32,64}")

SUBJECT_FORMAT = "Enter the primary address of a Google Workspace user: plain ASCII, no '+' tag, no display name."
ACTIVE_NEEDS_KEY = "Install the service-account key before activating this configuration."
TAKEOVER_REFUSED = (
    "Mail → Notification Delivery sends email through the Gmail API, so this configuration can become the active "
    "one only when email could switch to it: {problem}"
)
RUN_THE_CHECK = "run the access check (Run access check on this page, or manage.py verify_gmail_access)"
# The ceilings themselves are GMAIL_API settings (a deployment may override them); the admin form names the values.
RECIPIENTS_HELP = "Recipients one message may have (To and Cc)."
MESSAGE_BYTES_HELP = "Size of the encoded message."
CEILING_HELP = "At most Google's documented limit; it can be lowered here, not raised."


def default_max_recipients() -> int:
    return settings.GMAIL_API["max_recipients_per_message"]


def default_max_message_bytes() -> int:
    return settings.GMAIL_API["max_message_bytes"]


def normalize_subject(value) -> str:
    """Google account addresses compare case-insensitively."""
    return str(value or "").strip().lower()


def is_subject(value) -> bool:
    """A plain ASCII address with no ``+`` tag: the form of a Workspace user's primary address."""
    text = str(value or "")
    return text.isascii() and "+" not in text and len(text) <= 254 and is_plain_address(text)


class GmailApiProviderConfig(ProjectControlModel):
    """A Google service account with domain-wide delegation for ``gmail.send``, used to send email as Workspace users.

    The site impersonates only the accounts on the subject allow-list (``GmailApiSubject``), and always sends From
    the impersonated account. The service-account key lives in the credential store (AWS Secrets Manager in
    production); this row keeps only a pointer to the pinned stored version and the key's public facts. Keys are
    installed and removed on their own admin pages, by superusers only.
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
        from .email import EmailServiceConfig  # email.py imports this module

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

    @property
    def key_configured(self) -> bool:
        """A pinned stored key and well-formed public facts. Nothing here reads the key."""
        account = SERVICE_ACCOUNT_EMAIL_RE.fullmatch(self.service_account_email or "")
        return bool(
            self.key_secret_ref
            and VERSION_ID_RE.fullmatch(self.key_version_id or "")
            and account
            and account.group("project") == self.project_id
            and CLIENT_ID_RE.fullmatch(self.client_id or "")
            and KEY_ID_RE.fullmatch(self.key_id or "")
        )

    @property
    def is_configured(self) -> bool:
        return bool(not self._state.adding and self.is_active and self.key_configured and self.subjects.exists())

    def allows(self, address: str) -> bool:
        """Whether *address* is on the subject allow-list (the only accounts the site impersonates)."""
        if not address or self._state.adding:
            return False
        return self.subjects.filter(subject=normalize_subject(address)).exists()

    def sending_ready(self, from_email: str) -> bool:
        """Configured, and the From address is on the allow-list (the site always sends From the subject)."""
        return self.is_configured and self.allows(from_email)

    @property
    def access_check_current(self) -> bool:
        """The access check passed after the installed key was installed."""
        return bool(
            self.key_installed_at and self.access_checked_at and self.access_checked_at >= self.key_installed_at
        )

    def subject_verified(self, address: str) -> bool:
        """Google issued a gmail.send token for *address* with the installed key (the access check)."""
        if not self.key_installed_at or self._state.adding:
            return False
        subject = self.subjects.filter(subject=normalize_subject(address)).first()
        return bool(subject and subject.verified_at and subject.verified_at >= self.key_installed_at)

    def activation_problem(self, from_email: str) -> str:
        """Why email may not switch to the Gmail API with *from_email* as the From address yet, or ""."""
        if not self.sending_ready(from_email):
            return "the configuration is not active with an installed key and the From address on its allow-list."
        if not self.access_check_current:
            return f"no access check has passed for the installed key; {RUN_THE_CHECK}."
        if not self.subject_verified(from_email):
            return f"the access check has not verified the From address with the installed key; {RUN_THE_CHECK}."
        return ""


class GmailApiSubject(ProjectControlModel):
    """One Google account the site may impersonate (and send From). Google cannot restrict domain-wide delegation
    per user, so this list is the only per-user control: it guards against site errors, not against a key holder."""

    config = models.ForeignKey(GmailApiProviderConfig, on_delete=models.CASCADE, related_name="subjects")
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
