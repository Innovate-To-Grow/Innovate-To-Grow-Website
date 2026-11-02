"""What mail staff set for each delivery channel on Mail → Delivery Rates: the Smart rate switch, the manual rate
and the provider limits."""

from decimal import Decimal
from typing import NamedTuple

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import DomainNameValidator, MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from .control import ProjectControlModel

# Marked for translation; the site ships no translations yet, so they render as written.
SMART_RATE_HELP = _(
    "Adjusts the rate automatically to actual conditions. It uses the limit the provider reports (where it reports "
    "one), slows down as soon as the provider throttles or pushes back, then speeds up again step by step, never "
    "above the provider limit. While Smart rate is on it takes priority over the manual rate; the manual rate is "
    "kept and is used again when you turn Smart rate off."
)
MANUAL_RATE_HELP = _(
    "Fixed rate used while Smart rate is off. It cannot be set above the provider limit (Advanced). Pauses the "
    "provider explicitly asks for, and daily limits, still apply."
)
NO_INTERNAL_DOMAIN = "No account is on a Gmail API allow-list yet, so no domain can count as internal; leave it blank."
INTERNAL_DOMAIN_REFUSED = (
    "It must be the domain of an account on a Gmail API allow-list, or a parent domain of it ({allowed}). Any other "
    "domain would stop its recipients counting against Google's external-recipient limit."
)

# Column shapes (schema, not tunables): rates keep three decimal places, so 0.001 is the slowest storable rate; the
# budget headroom and the reserve are shares with three decimal places.
RATE_DIGITS = 10
RATE_PLACES = 3
SHARE_DIGITS = 4
MIN_RATE = Decimal("0.001")
MAX_RESERVE = Decimal("0.999")
DOMAIN_VALIDATOR = DomainNameValidator(accept_idna=False)


class RateUnit(NamedTuple):
    """What a channel's rates count and per how many seconds, and what its daily budget counts."""

    label: str
    per_seconds: int
    budget: str = "recipients"


class DeliveryChannel(models.TextChoices):
    GRAPH_SEND = "graph_send", "Email · Microsoft Graph"
    GRAPH_READ = "graph_read", "Inbox · Microsoft Graph"
    SES_SEND = "ses_send", "Email · Amazon SES"
    SMTP_SEND = "smtp_send", "Email · SMTP"
    GMAIL_IMAP = "gmail_imap", "Inbox · Gmail"
    GMAIL_API_SEND = "gmail_api_send", "Email · Gmail API"
    SMS_SEND = "sms_send", "SMS · AWS End User Messaging"


# The unit each channel's stored rates are in. Changing one would reinterpret every stored value, so it is part of
# the schema rather than a setting.
CHANNEL_UNITS = {
    DeliveryChannel.GRAPH_SEND: RateUnit("messages/min", 60),
    DeliveryChannel.GRAPH_READ: RateUnit("requests/min", 60, budget=""),
    DeliveryChannel.SES_SEND: RateUnit("recipients/sec", 1),
    DeliveryChannel.SMTP_SEND: RateUnit("messages/min", 60),
    DeliveryChannel.GMAIL_IMAP: RateUnit("sessions/min", 60, budget=""),
    DeliveryChannel.GMAIL_API_SEND: RateUnit("messages/min", 60),
    DeliveryChannel.SMS_SEND: RateUnit("messages/sec", 1, budget="messages"),
}

# Fields only some channels have; a channel has one when its DELIVERY_RATES seed lists it. Elsewhere it stays empty.
OPTIONAL_FIELDS = (
    "parts_limit",
    "daily_limit",
    "hourly_external_limit",
    "hourly_internal_limit",
    "limits_confirmed",
    "daily_message_limit",
    "daily_external_limit",
    "internal_domain",
    "budget_headroom",
    "transactional_reserve",
)
SEED_FIELDS = ("smart_enabled", "manual_rate", "provider_limit", *OPTIONAL_FIELDS)
# Documented provider limits: the DELIVERY_RATES value seeds the field and is also its ceiling.
CEILING_FIELDS = (
    "provider_limit",
    "parts_limit",
    "daily_limit",
    "hourly_external_limit",
    "hourly_internal_limit",
    "daily_message_limit",
    "daily_external_limit",
)
DECIMAL_FIELDS = frozenset({"manual_rate", "provider_limit", "parts_limit", "budget_headroom", "transactional_reserve"})


def _rate_field(verbose_name, help_text, **options):
    return models.DecimalField(
        max_digits=RATE_DIGITS,
        decimal_places=RATE_PLACES,
        validators=[MinValueValidator(MIN_RATE)],
        verbose_name=verbose_name,
        help_text=help_text,
        **options,
    )


def _limit_field(verbose_name, help_text):
    return models.PositiveIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1)], verbose_name=verbose_name, help_text=help_text
    )


def _as_number(value):
    """``value`` as a Decimal, or None when it is empty or not a number (its field error is reported already)."""
    if isinstance(value, bool) or not isinstance(value, int | float | Decimal):
        return None
    return Decimal(str(value))


def display_number(value: Decimal) -> str:
    """``Decimal("30.000")`` as "30", ``Decimal("10000")`` as "10,000", ``Decimal("0.500")`` as "0.5"."""
    return f"{value.normalize():,f}"


def allow_list_domains() -> set[str]:
    """The domain of every account on a Gmail API allow-list (superusers keep those lists) and its parent domains of
    two labels or more: ``i2g@g.ucmerced.edu`` gives ``g.ucmerced.edu`` and ``ucmerced.edu``."""
    from .service_credentials.gmail_api import GmailApiSubject

    found = set()
    for subject in GmailApiSubject.objects.values_list("subject", flat=True):
        labels = subject.rpartition("@")[2].lower().split(".")
        found.update(".".join(labels[start:]) for start in range(len(labels) - 1))
    return found


def seed_value(field: str, value):
    """A DELIVERY_RATES seed in the form its column stores."""
    if field in DECIMAL_FIELDS and value is not None:
        return Decimal(str(value)).quantize(MIN_RATE)
    return value


class DeliveryRatePolicy(ProjectControlModel):
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
    def channel_settings(channel: str) -> dict:
        """The channel's ``DELIVERY_RATES`` seeds and ceilings."""
        return settings.DELIVERY_RATES["channels"][channel]

    @classmethod
    def seed_values(cls, channel: str) -> dict:
        spec = cls.channel_settings(channel)
        return {field: seed_value(field, spec[field]) for field in SEED_FIELDS if field in spec}

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

    def _check_applicable(self, spec, errors):
        for name in OPTIONAL_FIELDS:
            if name not in spec and getattr(self, name) != self._meta.get_field(name).get_default():
                errors[name] = f"{self.get_channel_display()} has no such limit; leave it empty."

    def _limit_unit(self, name: str) -> str:
        budget = self.unit.budget
        return {
            "provider_limit": self.unit.label,
            "parts_limit": "parts/sec",
            "daily_limit": f"{budget} per 24 h",
            "hourly_external_limit": "external recipients per hour",
            "hourly_internal_limit": "internal recipients per hour",
            "daily_message_limit": "messages per 24 h",
            "daily_external_limit": "external recipients per 24 h",
        }[name]

    def _check_ceilings(self, spec, errors):
        for name in CEILING_FIELDS:
            ceiling, value = _as_number(spec.get(name)), _as_number(getattr(self, name))
            if ceiling is not None and value is not None and value > ceiling:
                errors.setdefault(
                    name,
                    f"The documented limit is {display_number(ceiling)} {self._limit_unit(name)}. It can be lowered here, "
                    "not raised.",
                )

    def _check_manual_rate(self, spec, errors):
        manual = _as_number(self.manual_rate)
        bound = _as_number(self.provider_limit)
        if bound is None:
            bound = _as_number(spec["provider_limit"])
        if manual is not None and bound is not None and manual > bound:
            errors.setdefault(
                "manual_rate",
                f"It cannot be set above the provider limit of {display_number(bound)} {self.unit.label} (Advanced).",
            )

    def _check_daily_limits(self, spec, errors):
        daily = _as_number(self.daily_limit)
        if daily is None:
            daily = _as_number(spec.get("daily_limit"))
        if daily is None:
            return
        for name in ("hourly_external_limit", "hourly_internal_limit", "daily_external_limit"):
            value = _as_number(getattr(self, name))
            if value is not None and value > daily:
                errors.setdefault(
                    name, f"It cannot be above the daily limit of {display_number(daily)} {self.unit.budget}."
                )

    def _check_internal_domain(self, spec, errors):
        """Recipients in the internal domain do not count against Google's external limit, so naming one raises that
        limit: only the deployer's seed, or the domain of an allow-listed account (or a parent of it), may be named."""
        domain = self.internal_domain
        if not domain or "internal_domain" in errors or domain == str(spec.get("internal_domain") or "").lower():
            return
        try:
            DOMAIN_VALIDATOR(domain)
        except ValidationError:
            return  # the field's own validation reports it
        allowed = allow_list_domains()
        if domain not in allowed:
            listed = ", ".join(sorted(allowed))
            errors["internal_domain"] = (
                INTERNAL_DOMAIN_REFUSED.format(allowed=listed) if allowed else NO_INTERNAL_DOMAIN
            )
