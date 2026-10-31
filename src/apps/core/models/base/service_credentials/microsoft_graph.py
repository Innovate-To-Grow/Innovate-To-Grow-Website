from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.utils import timezone

from apps.core.utils.security import is_entra_tenant, is_exchange_mailbox, is_guid

from ..control import ProjectControlModel
from .microsoft_graph_certificate import MicrosoftGraphCertificate

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
    """The Entra app used to send and read email through Microsoft Graph (Outlook / Exchange Online).

    The app authenticates only with a certificate. Its public data and a pointer to the private key live in
    ``MicrosoftGraphCertificate`` rows (one current, one previous for rollback); the key itself is kept in the
    credential store, never in this table.
    """

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
        changed = self._application_field_changed_under_a_certificate()
        if changed:
            errors.setdefault(
                changed,
                "Remove the installed certificates before changing the Entra application, then install the "
                "certificate registered for the new application.",
            )
        if errors:
            raise ValidationError(errors)

    def _application_field_changed_under_a_certificate(self) -> str:
        """A certificate is tested for one tenant and app, so it never silently follows a change of either.

        Returns the name of the changed field while a current or previous certificate is installed, else "".
        """
        if self._state.adding:
            return ""
        stored = type(self).objects.filter(pk=self.pk).values_list("tenant_id", "client_id").first()
        if stored is None or stored == (self.tenant_id, self.client_id):
            return ""
        if not self.certificates.filter(state__in=MicrosoftGraphCertificate.LIVE_STATES).exists():
            return ""
        return "tenant_id" if stored[0] != self.tenant_id else "client_id"

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
    def current_certificate(self):
        """The certificate the site signs with, or None."""
        if self._state.adding:
            return None
        return self.certificates.filter(state=MicrosoftGraphCertificate.State.CURRENT).first()

    @property
    def previous_certificate(self):
        """The certificate the current one replaced, kept for rollback, or None."""
        if self._state.adding:
            return None
        return self.certificates.filter(state=MicrosoftGraphCertificate.State.PREVIOUS).first()

    @property
    def certificate_expires_at(self):
        certificate = self.current_certificate
        return certificate.not_after if certificate is not None else None

    @property
    def certificate_expired(self) -> bool:
        expires_at = self.certificate_expires_at
        return expires_at is not None and expires_at <= timezone.now()

    @property
    def credential_configured(self) -> bool:
        """A current certificate, valid now and tested for this tenant and app, pins a stored private key."""
        certificate = self.current_certificate
        return certificate is not None and certificate.usable_for(self)

    @property
    def is_configured(self):
        """Active, saved, well-formed and scoped, so readiness gates agree with what the Graph services accept."""
        return self._configured()

    def _configured(self, scopes=None) -> bool:
        if self._state.adding or not self.is_active:
            return False
        well_formed = (
            is_entra_tenant(self.tenant_id)
            and is_guid(self.client_id)
            and (not self.mailbox or is_exchange_mailbox(self.mailbox))
        )
        return bool(
            well_formed and self.credential_configured and (self.mailbox_scopes.exists() if scopes is None else scopes)
        )

    def sender_mailbox(self, from_email: str) -> str:
        """The mailbox Graph sends as (and whose inbox the admin reads): the configured one or the From address."""
        return normalize_mailbox(self.mailbox or from_email)

    def allows(self, mailbox: str, permission: str, *, scopes=None) -> bool:
        """Whether *mailbox* is in this config's scope with *permission* (``"send"`` or ``"read"``).

        *scopes* (``{mailbox: permission level}``) stands in for the stored scope, to check a change before it is saved.
        """
        if not mailbox:
            return False
        if scopes is not None:
            return MicrosoftGraphMailboxScope.level_grants(scopes.get(normalize_mailbox(mailbox)), permission)
        if self._state.adding:
            return False
        scope = self.mailbox_scopes.filter(mailbox=normalize_mailbox(mailbox)).first()
        return scope is not None and scope.grants(permission)

    def sending_ready(self, from_email: str, *, scopes=None) -> bool:
        """Configured, and both the sending mailbox and the From address may send (*scopes*: see ``allows``)."""
        if not self._configured(scopes):
            return False
        sender = self.sender_mailbox(from_email)
        return self.allows(sender, "send", scopes=scopes) and (
            sender == normalize_mailbox(from_email) or self.allows(from_email, "send", scopes=scopes)
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
        return self.level_grants(self.permission, permission)

    @classmethod
    def level_grants(cls, level, permission: str) -> bool:
        """Whether the permission level *level* (a ``Permission`` value, or None) includes *permission*."""
        if permission == "send":
            return level in (cls.Permission.SEND, cls.Permission.SEND_AND_READ)
        if permission == "read":
            return level in (cls.Permission.READ, cls.Permission.SEND_AND_READ)
        return False
