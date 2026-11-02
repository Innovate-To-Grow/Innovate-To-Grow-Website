"""What staff set for each request-limit scope: the Smart limit switch, the manual limit, the priority tier and the
deployer ceilings. Seeded from ``REQUEST_RATE_LIMITS["scopes"]``."""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from .control import ProjectControlModel

# Marked for translation; the site ships no translations yet, so they render as written. Mirrors the delivery-rate
# wording ("智能限流：根据实际情况（负载、错误率、滥用）自动调整限额").
SMART_LIMIT_HELP = _(
    "Adjusts the limit automatically to actual conditions (load, error rate, abuse). Under overload it tightens "
    "heavy and background requests first and interactive ones last, never sign-in and verification codes, then "
    "relaxes step by step when the site is healthy, never below the Smart floor. While Smart limit is on it takes "
    "priority over the manual limit; the manual limit is kept and is used again when you turn Smart limit off."
)
MANUAL_LIMIT_HELP = _(
    "Requests one caller may make per period while Smart limit is off. It cannot be set above the per-caller "
    "ceiling. The finer per-view limits (code cooldowns, sign-in lockout, SMS budget) still apply."
)
MAX_PERIOD_SECONDS = 86_400
SHARE_DIGITS = 4
SHARE_PLACES = 3
SEED_FIELDS = (
    "label",
    "description",
    "tier",
    "identity",
    "manual_requests",
    "period_seconds",
    "smart_enabled",
    "smart_floor",
    "fixed",
    "enabled",
    "identity_ceiling",
    "global_cap",
)
# Deployer maximums: the REQUEST_RATE_LIMITS value seeds the field and is also its ceiling.
CEILING_FIELDS = ("identity_ceiling", "global_cap")


class RequestTier(models.TextChoices):
    P0 = "p0", "P0 critical"
    P1 = "p1", "P1 interactive"
    P2 = "p2", "P2 background"
    P3 = "p3", "P3 heavy"


class IdentityKind(models.TextChoices):
    MEMBER = "member", "Signed-in member (never IP)"
    SESSION = "session", "Admin user"
    CLI = "cli", "CLI token"
    IP = "ip", "Signed-in user, else client IP"
    DESTINATION = "destination", "Code destination, else member"
    GLOBAL = "global", "Everyone together"


def scope_seed(scope: str, spec: dict) -> dict:
    """A ``REQUEST_RATE_LIMITS`` scope in the form the policy columns store."""
    floor = spec["smart_floor"]
    if floor is None:
        floor = settings.REQUEST_RATE_LIMITS["tiers"][spec["tier"]].get("floor", 1)
    values = {key: spec[key] for key in SEED_FIELDS if key in spec}
    values["manual_requests"] = spec["requests"]
    values["smart_floor"] = Decimal(str(floor)).quantize(Decimal("0.001"))
    return values


class RequestRateLimitPolicy(ProjectControlModel):
    """One scope's request limit. The live Smart factor is ``RequestRateLimitState``; this row is what people set."""

    Tier = RequestTier
    Identity = IdentityKind

    scope = models.CharField(max_length=64, unique=True, verbose_name="Scope")
    label = models.CharField(max_length=120, verbose_name="Name")
    description = models.TextField(blank=True, default="", verbose_name="What it covers")
    tier = models.CharField(
        max_length=2,
        choices=RequestTier.choices,
        default=RequestTier.P1,
        verbose_name="Priority",
        help_text="Under overload Smart limit sheds P3 first, then P2, then P1; P0 only by its abuse limits.",
    )
    identity = models.CharField(
        max_length=16, choices=IdentityKind.choices, default=IdentityKind.IP, verbose_name="Counted per"
    )
    manual_requests = models.PositiveIntegerField(
        validators=[MinValueValidator(1)], verbose_name="Manual limit", help_text=MANUAL_LIMIT_HELP
    )
    period_seconds = models.PositiveIntegerField(
        default=60,
        validators=[MinValueValidator(1), MaxValueValidator(MAX_PERIOD_SECONDS)],
        verbose_name="Period (seconds)",
    )
    smart_enabled = models.BooleanField(default=True, verbose_name="Smart limit", help_text=SMART_LIMIT_HELP)
    smart_floor = models.DecimalField(
        max_digits=SHARE_DIGITS,
        decimal_places=SHARE_PLACES,
        default=Decimal("0.500"),
        validators=[MinValueValidator(Decimal("0.001")), MaxValueValidator(Decimal(1))],
        verbose_name="Smart floor",
        help_text="Smart limit never goes below this share of the scope's baseline.",
    )
    fixed = models.BooleanField(
        default=False, verbose_name="Fixed", help_text="Smart limit never tightens this scope (it still relaxes it)."
    )
    enabled = models.BooleanField(default=True, verbose_name="Enabled", help_text="Off: requests are not limited.")
    identity_ceiling = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        verbose_name="Per-caller ceiling",
        help_text="Most requests one caller may make per period, whatever the mode. Blank: no ceiling.",
    )
    global_cap = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        verbose_name="Everyone together",
        help_text="Most requests all callers together may make per period (Smart limit scales it). Blank: none.",
    )

    class Meta:
        verbose_name = "Request Limit Policy"
        verbose_name_plural = "Request Limit Policies"
        ordering = ("tier", "scope")

    def __str__(self):
        mode = "Smart limit" if self.smart_enabled else f"{self.manual_requests}/{self.period_seconds}s"
        return f"{self.label} ({self.get_tier_display()}): {mode}"

    @staticmethod
    def scope_settings(scope: str) -> dict:
        return settings.REQUEST_RATE_LIMITS["scopes"][scope]

    @classmethod
    def seed_values(cls, scope: str) -> dict:
        return scope_seed(scope, cls.scope_settings(scope))

    @classmethod
    def for_scope(cls, scope: str) -> "RequestRateLimitPolicy":
        """The scope's row, created from ``REQUEST_RATE_LIMITS`` when missing (a deleted row heals itself)."""
        if scope not in settings.REQUEST_RATE_LIMITS["scopes"]:
            raise ValueError(f"Unknown request-limit scope: {scope!r}")
        policy, _created = cls.objects.get_or_create(scope=scope, defaults=cls.seed_values(scope))
        return policy

    def clean(self):
        super().clean()
        spec = settings.REQUEST_RATE_LIMITS["scopes"].get(self.scope)
        if spec is None:
            raise ValidationError({"scope": "This scope is not in REQUEST_RATE_LIMITS; add it there first."})
        errors = {}
        for name in CEILING_FIELDS:
            ceiling, value = spec[name], getattr(self, name)
            if ceiling is not None and (value is None or value > ceiling):
                errors[name] = f"The deployment allows at most {ceiling:,}. It can be lowered here, not raised."
        ceiling = self.identity_ceiling
        if ceiling is not None and self.manual_requests is not None and self.manual_requests > ceiling:
            errors.setdefault("manual_requests", f"It cannot be set above the per-caller ceiling of {ceiling:,}.")
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # The unique scope is left to the database so concurrent heals recover through get_or_create.
        self.full_clean(validate_unique=False)
        super().save(*args, **kwargs)
