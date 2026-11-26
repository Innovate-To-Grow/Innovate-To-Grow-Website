"""The policy's help texts, column shapes and field groups, and the helpers that build and read its fields."""

from decimal import Decimal

from django.core.validators import DomainNameValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

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
# A channel spec whose ceilings were entered on the provider's configuration (Microsoft Graph's mailbox limits from
# OIT) carries this marker; ``services.delivery_rates.rules.tenant`` sets it.
LIMITS_SOURCE_KEY = "limits_source"
TENANT_LIMITS = "tenant"


def limits_from_configuration(spec: dict) -> bool:
    return spec.get(LIMITS_SOURCE_KEY) == TENANT_LIMITS


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
    """The domain of every account on a Gmail API allow-list (Admins keep those lists) and its parent domains of
    two labels or more: ``i2g@g.ucmerced.edu`` gives ``g.ucmerced.edu`` and ``ucmerced.edu``."""
    from ..service_credentials.gmail_api import GmailApiSubject

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
