from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.utils import timezone

from apps.core.utils.security import is_entra_tenant, is_exchange_mailbox, is_guid

from ..control import ProjectControlModel

# Exchange Online limits for one sender mailbox (Microsoft Learn: "Exchange Online limits").
GRAPH_MAX_MESSAGES_PER_MINUTE = 30
GRAPH_DEFAULT_MESSAGES_PER_MINUTE = 24
GRAPH_DAILY_RECIPIENT_LIMIT = 10_000
# Emails one admin request may send inline (outside the paced queue) while Graph is the provider.
GRAPH_INLINE_BATCH_LIMIT = 20


def normalize_mailbox(value: str) -> str:
    """Exchange addresses, UPNs and object IDs compare case-insensitively."""
    return str(value or "").strip().lower()


class MicrosoftGraphProviderConfig(ProjectControlModel):
    """Entra app credentials used to send and read email through Microsoft Graph (Outlook / Exchange Online)."""

    class AuthMethod(models.TextChoices):
        CERTIFICATE = "certificate", "Certificate (recommended)"
        CLIENT_SECRET = "client_secret", "Client secret"

    name = models.CharField(max_length=128, default="Default", verbose_name="Config Name")
    is_active = models.BooleanField(
        default=False,
        verbose_name="Active",
        help_text="Only one Microsoft Graph config can be active. Activating this will deactivate others.",
    )
    tenant_id = models.CharField(
        max_length=253,
        verbose_name="Tenant ID",
        help_text="Directory (tenant) ID as a GUID, or a verified domain such as contoso.onmicrosoft.com.",
    )
    client_id = models.CharField(
        max_length=64,
        verbose_name="Client ID",
        help_text="Application (client) ID of the Entra app registration.",
    )
    auth_method = models.CharField(
        max_length=16,
        choices=AuthMethod.choices,
        default=AuthMethod.CERTIFICATE,
        verbose_name="Authentication",
        help_text="How the app proves its identity to Microsoft Entra ID.",
    )
    client_secret = models.CharField(
        max_length=256,
        blank=True,
        default="",
        verbose_name="Client Secret",
        help_text="Client secret value (not the secret ID). Secrets expire, so rotate before the expiry date.",
    )
    certificate = models.TextField(
        blank=True,
        default="",
        verbose_name="Certificate (PEM)",
        help_text="Public X.509 certificate uploaded to the Entra app, PEM encoded (-----BEGIN CERTIFICATE-----).",
    )
    private_key = models.TextField(
        blank=True,
        default="",
        verbose_name="Private Key (PEM)",
        help_text="Unencrypted RSA private key of the certificate, PEM encoded. It never leaves the server.",
    )
    certificate_thumbprint = models.CharField(
        max_length=64,
        blank=True,
        default="",
        editable=False,
        verbose_name="Certificate SHA-256 Thumbprint",
    )
    certificate_expires_at = models.DateTimeField(
        null=True, blank=True, editable=False, verbose_name="Certificate Expires"
    )
    mailbox = models.CharField(
        max_length=254,
        blank=True,
        default="",
        verbose_name="Sender Mailbox",
        help_text=(
            "Email address / user principal name (or object ID) of the Exchange Online mailbox that sends mail "
            "and whose inbox the admin reads. Leave blank to use the From email address. It must be listed in "
            "the mailbox scope below."
        ),
    )
    messages_per_minute = models.PositiveSmallIntegerField(
        default=GRAPH_DEFAULT_MESSAGES_PER_MINUTE,
        validators=[MinValueValidator(1), MaxValueValidator(GRAPH_MAX_MESSAGES_PER_MINUTE)],
        verbose_name="Messages per Minute",
        help_text=(
            f"Exchange Online allows {GRAPH_MAX_MESSAGES_PER_MINUTE} messages per minute per mailbox. "
            "Keep this below that limit so login codes and tickets are not throttled during campaigns."
        ),
    )

    class Meta:
        verbose_name = "Microsoft Graph Provider Config"
        verbose_name_plural = "Microsoft Graph Provider Configs"
        constraints = [
            models.UniqueConstraint(
                fields=["is_active"],
                condition=models.Q(is_active=True),
                name="core_one_active_graph_provider_config",
            ),
        ]

    def __str__(self):
        status = " (active)" if self.is_active else ""
        target = self.mailbox or self.client_id or "not configured"
        return f"{self.name}: {target}{status}"

    def clean(self):
        super().clean()
        errors = {}
        if self.tenant_id and not is_entra_tenant(self.tenant_id):
            errors["tenant_id"] = "Use the tenant GUID or a verified domain such as contoso.onmicrosoft.com."
        if self.client_id and not is_guid(self.client_id):
            errors["client_id"] = "The application (client) ID must be a GUID."
        if self.mailbox and not is_exchange_mailbox(self.mailbox):
            errors["mailbox"] = "Enter the mailbox email address / user principal name, or its object ID (GUID)."
        if self.auth_method == self.AuthMethod.CERTIFICATE:
            errors.update(self._clean_certificate())
        elif self.is_active and not self.client_secret:
            errors["client_secret"] = "A client secret is required for an active configuration."  # nosec B105 — validation message, not a credential
        if errors:
            raise ValidationError(errors)

    def _clean_certificate(self) -> dict[str, str]:
        """Check the PEM pair and record its thumbprint and expiry, which the token request and monitoring use."""
        from apps.core.services.email.graph.certificate import CertificateError, inspect_pair

        self.certificate, self.private_key = self.certificate.strip(), self.private_key.strip()
        self.certificate_thumbprint, self.certificate_expires_at = "", None
        if not (self.certificate or self.private_key):
            return {"certificate": "A certificate and its private key are required."} if self.is_active else {}
        if not (self.certificate and self.private_key):
            field = "private_key" if self.certificate else "certificate"
            return {field: "Enter both the certificate and its private key."}
        try:
            info = inspect_pair(self.certificate, self.private_key)
        except CertificateError as exc:
            return {"certificate": str(exc)}
        self.certificate_thumbprint, self.certificate_expires_at = info.thumbprint, info.not_after
        if self.is_active and info.not_after <= timezone.now():
            return {"certificate": "This certificate has expired. Upload a new one to Entra and enter it here."}
        return {}

    def validate_constraints(self, exclude=None):
        # save() replaces the active row atomically. Do not reject that switch
        # during ModelForm validation; the database still enforces uniqueness.
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
        """Return the active Microsoft Graph provider, or an unsaved instance with defaults."""
        try:
            return cls.objects.get(is_active=True)
        except cls.DoesNotExist:
            return cls()

    @property
    def uses_certificate(self) -> bool:
        return self.auth_method == self.AuthMethod.CERTIFICATE

    @property
    def certificate_expired(self) -> bool:
        return self.certificate_expires_at is not None and self.certificate_expires_at <= timezone.now()

    @property
    def credential_configured(self) -> bool:
        if self.uses_certificate:
            has_pair = self.certificate and self.private_key and self.certificate_thumbprint
            return bool(has_pair and not self.certificate_expired)
        return bool(self.client_secret)

    @property
    def is_configured(self):
        """Active, saved, well-formed and scoped, so readiness gates agree with what the Graph services accept."""
        return bool(
            not self._state.adding
            and self.is_active
            and is_entra_tenant(self.tenant_id)
            and is_guid(self.client_id)
            and self.credential_configured
            and (not self.mailbox or is_exchange_mailbox(self.mailbox))
            and self.mailbox_scopes.exists()
        )

    def sender_mailbox(self, from_email: str) -> str:
        """The mailbox Graph sends as (and whose inbox the admin reads): the configured one or the From address."""
        return normalize_mailbox(self.mailbox or from_email)

    def allows(self, mailbox: str, permission: str) -> bool:
        """Whether *mailbox* is in this config's scope with *permission* (``"send"`` or ``"read"``)."""
        if self._state.adding or not mailbox:
            return False
        scope = self.mailbox_scopes.filter(mailbox=normalize_mailbox(mailbox)).first()
        return scope is not None and scope.grants(permission)

    def sending_ready(self, from_email: str) -> bool:
        """Configured, and both the sending mailbox and the From address may send."""
        if not self.is_configured:
            return False
        sender = self.sender_mailbox(from_email)
        return self.allows(sender, "send") and (
            sender == normalize_mailbox(from_email) or self.allows(from_email, "send")
        )


class MicrosoftGraphMailboxScope(ProjectControlModel):
    """One mailbox the Graph app may use, with the permission level the site may exercise on it.

    The site refuses any Graph request for a mailbox or permission not listed here. This mirrors, and does not
    replace, the Exchange Online RBAC for Applications scope that Microsoft enforces for the Entra app.
    """

    class Permission(models.TextChoices):
        SEND = "send", "Send only (Mail.Send)"
        READ = "read", "Read only (Mail.Read)"
        SEND_AND_READ = "send_read", "Send and read (Mail.Send + Mail.Read)"

    config = models.ForeignKey(MicrosoftGraphProviderConfig, on_delete=models.CASCADE, related_name="mailbox_scopes")
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
        help_text="Must match the Exchange Online role assignments for this mailbox.",
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
        if permission == "send":
            return self.permission in (self.Permission.SEND, self.Permission.SEND_AND_READ)
        if permission == "read":
            return self.permission in (self.Permission.READ, self.Permission.SEND_AND_READ)
        return False
