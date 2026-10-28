from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction

from apps.core.utils.security import is_entra_tenant, is_exchange_mailbox, is_guid

from ..control import ProjectControlModel

# Exchange Online limits for one sender mailbox (Microsoft Learn: "Exchange Online limits").
GRAPH_MAX_MESSAGES_PER_MINUTE = 30
GRAPH_DEFAULT_MESSAGES_PER_MINUTE = 24
GRAPH_DAILY_RECIPIENT_LIMIT = 10_000
# Emails one admin request may send inline (outside the paced queue) while Graph is the provider.
GRAPH_INLINE_BATCH_LIMIT = 20


class MicrosoftGraphProviderConfig(ProjectControlModel):
    """Entra app credentials used to send email through Microsoft Graph (Outlook / Exchange Online)."""

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
    client_secret = models.CharField(
        max_length=256,
        blank=True,
        default="",
        verbose_name="Client Secret",
        help_text="Client secret value (not the secret ID). Secrets expire, so rotate before the expiry date.",
    )
    mailbox = models.CharField(
        max_length=254,
        blank=True,
        default="",
        verbose_name="Sender Mailbox",
        help_text=(
            "Email address / user principal name (or object ID) of the Exchange Online mailbox that sends mail. "
            "Leave blank to use the From email address."
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
        if self.is_active and not self.client_secret:
            errors["client_secret"] = "A client secret is required for an active configuration."  # nosec B105 — validation message, not a credential
        if errors:
            raise ValidationError(errors)

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
    def is_configured(self):
        """Active, saved and well-formed, so readiness gates agree with what ``GraphProvider`` accepts."""
        return bool(
            not self._state.adding
            and self.is_active
            and is_entra_tenant(self.tenant_id)
            and is_guid(self.client_id)
            and self.client_secret
            and (not self.mailbox or is_exchange_mailbox(self.mailbox))
        )
