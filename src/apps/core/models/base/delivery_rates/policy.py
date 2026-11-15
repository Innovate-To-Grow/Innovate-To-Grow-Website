"""What mail staff set for each delivery channel on Mail → Delivery Rates: the Smart rate switch, the manual rate
and the provider limits."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from ..abstract.control import ProjectControlModel
from .channels import CHANNEL_UNITS, DeliveryChannel, RateUnit
from .fields import (
    CEILING_FIELDS,
    DOMAIN_VALIDATOR,
    MANUAL_RATE_HELP,
    MAX_RESERVE,
    MIN_RATE,
    RATE_PLACES,
    SEED_FIELDS,
    SHARE_DIGITS,
    SMART_RATE_HELP,
    _limit_field,
    _rate_field,
    limits_from_configuration,
    seed_value,
)
from .policy_checks import DeliveryRatePolicyChecksMixin


class DeliveryRatePolicy(DeliveryRatePolicyChecksMixin, ProjectControlModel):
    """One delivery channel's rate settings. The live pacing state is ``DeliveryRateState`` (per mailbox, account,
    host or number); this row is what people set.

    Smart rate takes priority over the manual rate while it is on, but the manual rate is always stored and never
    discarded. Every documented provider limit is capped by its ``DELIVERY_RATES`` value: it can be lowered here,
    never raised.
    """

    Channel = DeliveryChannel

    channel = models.CharField(max_length=32, unique=True, choices=DeliveryChannel.choices, verbose_name="Channel")
    smart_enabled = models.BooleanField(default=True, verbose_name="Smart rate", help_text=SMART_RATE_HELP)
    manual_rate = _rate_field("Manual rate", MANUAL_RATE_HELP)
    provider_limit = _rate_field(
        "Provider rate limit",
        "The provider's rate limit, in the channel's unit. Blank uses the limit the provider reports or documents.",
        null=True,
        blank=True,
    )
    # SES only, from migration 0036: ``provider_limit`` holds the previous release's campaign send rate, a stand-in
    # bound until AWS reports the account's own limit (the rate rule ignores it from then on). Saving another value,
    # or none, makes the field the operator's again.
    provider_limit_carried_over = models.BooleanField(
        default=False,
        editable=False,
        verbose_name="Provider limit carried over",
        help_text="The provider rate limit is the old campaign send rate, used only until the provider reports one.",
    )
    parts_limit = _rate_field(
        "Message parts per second (MPS)",
        "SMS only. Blank uses the rate AWS reports for the origination number.",
        null=True,
        blank=True,
    )
    daily_limit = _limit_field(
        "Daily limit (rolling 24 h)", "Recipients (SMS: messages) per rolling 24 hours. Blank uses the provider's."
    )
    hourly_external_limit = _limit_field(
        "Hourly external recipients", "Microsoft Graph only: the tenant's RecipientLimitExternalPerHour."
    )
    hourly_internal_limit = _limit_field(
        "Hourly internal recipients", "Microsoft Graph only: the tenant's RecipientLimitInternalPerHour."
    )
    limits_confirmed = models.BooleanField(
        default=False,
        verbose_name="Tenant limits confirmed",
        help_text=(
            "Microsoft Graph only. Tick once the tenant's outbound spam policy limits above are confirmed; until "
            "then campaigns also stay under the Standard preset's daily limit."
        ),
    )
    daily_message_limit = _limit_field("Daily messages (rolling 24 h)", "Messages per rolling 24 hours.")
    daily_external_limit = _limit_field(
        "Daily external recipients (rolling 24 h)", "Recipients outside the internal domain per rolling 24 hours."
    )
    internal_domain = models.CharField(
        max_length=253,
        blank=True,
        default="",
        validators=[DOMAIN_VALIDATOR],
        verbose_name="Internal domain",
        help_text="Gmail API only: the Workspace primary domain. Blank counts every recipient as external.",
    )
    budget_headroom = models.DecimalField(
        max_digits=SHARE_DIGITS,
        decimal_places=RATE_PLACES,
        default=Decimal("1.000"),
        validators=[MinValueValidator(MIN_RATE), MaxValueValidator(Decimal(1))],
        verbose_name="Daily budget headroom",
        help_text="Share of every daily limit the site uses (1 = all of it).",
    )
    transactional_reserve = models.DecimalField(
        max_digits=SHARE_DIGITS,
        decimal_places=RATE_PLACES,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal(0)), MaxValueValidator(MAX_RESERVE)],
        verbose_name="Transactional reserve",
        help_text="Share of every daily limit campaigns leave for login codes and tickets. Blank uses the default.",
    )

    class Meta:
        verbose_name = "Delivery Rate Policy"
        verbose_name_plural = "Delivery Rate Policies"
        ordering = ("channel",)

    def __str__(self):
        mode = "Smart rate" if self.smart_enabled else f"Manual {self.manual_rate} {self.unit.label}"
        return f"{self.get_channel_display()}: {mode}"

    @staticmethod
    def channel_settings(channel: str, *, configured: bool = True) -> dict:
        """The channel's ``DELIVERY_RATES`` seeds and ceilings, with the limits entered on the channel's provider
        configuration in place of the documented ones (Microsoft Graph); ``configured=False`` reads no database."""
        # Imported here: the rules import this module.
        from apps.core.services.delivery_rates.rules.defaults import channel_settings

        return channel_settings(channel, configured=configured)

    @classmethod
    def seed_values(cls, channel: str, *, configured: bool = True) -> dict:
        spec = cls.channel_settings(channel, configured=configured)
        seeds = {field: seed_value(field, spec[field]) for field in SEED_FIELDS if field in spec}
        if limits_from_configuration(spec):
            # Blank: the configuration's limits apply, and raising them there needs no second edit here.
            for field in CEILING_FIELDS:
                seeds.pop(field, None)
        return seeds

    @classmethod
    def for_channel(cls, channel: str) -> "DeliveryRatePolicy":
        """The channel's row, created from ``DELIVERY_RATES`` when it is missing (a deleted row heals itself)."""
        if channel not in DeliveryChannel.values:
            raise ValueError(f"Unknown delivery channel: {channel!r}")
        policy, _created = cls.objects.get_or_create(channel=channel, defaults=cls.seed_values(channel))
        return policy

    @property
    def unit(self) -> RateUnit:
        return CHANNEL_UNITS[self.channel]

    def clean_fields(self, exclude=None):
        # Normalize before the field validators see it: domains compare case-insensitively.
        self.internal_domain = str(self.internal_domain or "").strip().lower()
        if self.provider_limit is None:
            self.provider_limit_carried_over = False
        super().clean_fields(exclude=exclude)

    def clean(self):
        super().clean()
        if self.channel not in DeliveryChannel.values:
            return  # the field's choices validation reports it
        spec = self.channel_settings(self.channel)
        errors = {}
        self._check_applicable(spec, errors)
        self._check_ceilings(spec, errors)
        self._check_manual_rate(spec, errors)
        self._check_daily_limits(spec, errors)
        self._check_internal_domain(spec, errors)
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # The unique channel is left to the database: when two processes heal the same row at once, the second
        # insert must raise IntegrityError, which get_or_create recovers from, not a ValidationError it doesn't.
        self.full_clean(validate_unique=False)
        super().save(*args, **kwargs)
