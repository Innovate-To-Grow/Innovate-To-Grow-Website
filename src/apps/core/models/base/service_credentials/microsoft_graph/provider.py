"""The Entra app configuration: its fields, how it is saved, and which row is active."""

from django.core.validators import MinValueValidator
from django.db import models, transaction

from ...control import ProjectControlModel
from .limits import (
    _LIMITS_WHERE,
    default_external_recipients_per_hour_limit,
    default_internal_recipients_per_hour_limit,
    default_max_recipients_per_message,
    default_messages_per_minute_limit,
    default_recipients_per_day_limit,
)
from .provider_status import GraphProviderStatusMixin
from .provider_validation import GraphProviderValidationMixin


class MicrosoftGraphProviderConfig(GraphProviderValidationMixin, GraphProviderStatusMixin, ProjectControlModel):
    """The Entra app used to send and read email through Microsoft Graph (Outlook / Exchange Online).

    The app authenticates only with a certificate. Its public data and a pointer to the private key live in
    ``MicrosoftGraphCertificate`` rows (one current, one previous for rollback); the key itself is kept in the
    credential store, never in this table. ``MicrosoftGraphAccessCheck`` rows record each access check run.
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
    # Replaced by the graph_send policy (Mail → Delivery Rates), which migration 0036 seeded from it. Kept, not
    # editable, for one release so a task of the previous release (a rolling deploy, an image rollback) still finds
    # the column; the follow-up release drops it with EmailServiceConfig.max_send_rate. 24 is that release's own
    # default, so a row created now still reads as valid there.
    messages_per_minute = models.PositiveSmallIntegerField(
        default=24,
        editable=False,
        verbose_name="Messages per Minute",
        help_text="No longer used: rates are set under Mail → Delivery Rates.",
    )
    # The sender mailbox's sending limits as OIT states them. They bound the Graph delivery channel: the rate never
    # exceeds the messages per minute, the rolling budgets never the recipients per day or hour, and a message with
    # more recipients than allowed is refused before it is sent. Nothing here is a code constant: the seeds in
    # DELIVERY_RATES are only the initial values.
    max_recipients_per_message = models.PositiveIntegerField(
        default=default_max_recipients_per_message,
        validators=[MinValueValidator(1)],
        verbose_name="Recipients per Message Limit",
        help_text=(
            "Most recipients (To, Cc and Bcc together) one message may have, as OIT states it for the mailbox. "
            "A message with more is refused before it is sent. Campaign messages go to one recipient each."
        ),
    )
    messages_per_minute_limit = models.PositiveIntegerField(
        default=default_messages_per_minute_limit,
        validators=[MinValueValidator(1)],
        verbose_name="Messages per Minute Limit",
        help_text=(
            f"Most messages the mailbox may send per minute, as OIT states it. The rate under {_LIMITS_WHERE} never "
            "exceeds it: Smart rate uses a share of it, and the manual rate and the Advanced provider rate limit "
            "there can only be set below it."
        ),
    )
    recipients_per_day_limit = models.PositiveIntegerField(
        default=default_recipients_per_day_limit,
        validators=[MinValueValidator(1)],
        verbose_name="Recipients per Day Limit",
        help_text=(
            "Most recipients the mailbox may send to per rolling 24 hours, as OIT states it. Every email the site "
            "sends counts; campaigns stop before it (the transactional reserve) and their remaining recipients wait "
            f"until usage ages out. Until Tenant limits confirmed is ticked under {_LIMITS_WHERE}, campaigns also "
            "stay under the Standard outbound spam preset's daily limit."
        ),
    )
    external_recipients_per_hour_limit = models.PositiveIntegerField(
        null=True,
        blank=True,
        default=default_external_recipients_per_hour_limit,
        validators=[MinValueValidator(1)],
        verbose_name="External Recipients per Hour Limit",
        help_text=(
            "The outbound spam policy's limit on recipients outside the sender's domain per rolling hour "
            "(Microsoft's Standard preset: 500). Blank: no hourly limit. Confirm the tenant's value with OIT."
        ),
    )
    internal_recipients_per_hour_limit = models.PositiveIntegerField(
        null=True,
        blank=True,
        default=default_internal_recipients_per_hour_limit,
        validators=[MinValueValidator(1)],
        verbose_name="Internal Recipients per Hour Limit",
        help_text=(
            "The outbound spam policy's limit on recipients in the sender's domain per rolling hour (Microsoft's "
            "Standard preset: 1,000). Blank: no hourly limit. Confirm the tenant's value with OIT."
        ),
    )
    access_check_deny_mailbox = models.CharField(
        max_length=254,
        blank=True,
        default="",
        verbose_name="Access Check Deny Mailbox",
        help_text=(
            "An existing mailbox outside the scope, designated by OIT / InfoSec for the denial test (an email "
            "address, not another name of a scoped mailbox). The access check expects Microsoft to refuse reading "
            "it, sending as it and sending from it."
        ),
    )
    permission_exception_reference = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="InfoSec Exception Reference",
        help_text=(
            "Only after Graph application permissions beyond the approved ones (what OIT granted: Mail.ReadWrite "
            "and Mail.Send) have been approved in writing: the reference of that review (for example its ticket "
            "number). Set by an admin with the Core app; the site never fills it in."
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
