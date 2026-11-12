"""What one dashboard view covers: a time range (a preset or a custom day range), a provider, and the rows of each
telemetry table inside it. Every chart, figure and table on a page reads these same querysets, so they agree.

The access check's probe emails are diagnostics: the email log lists them under their own category, but they are
left out of every total, rate and chart.
"""

from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta

from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.core.models import EmailBounce, EmailCategory, OutboundEmail, OutboundEmailAttempt

PRESETS = {
    "24h": ("Last 24 hours", timedelta(hours=24)),
    "7d": ("Last 7 days", timedelta(days=7)),
    "30d": ("Last 30 days", timedelta(days=30)),
}
DEFAULT_RANGE = "7d"
MAX_CUSTOM_DAYS = 366
# Charts use hourly buckets up to this span, daily ones beyond it.
HOURLY_MAX_SPAN = timedelta(days=2)
PROVIDERS = {"graph": "Microsoft Graph", "ses": "Amazon SES", "smtp": "SMTP", "gmail": "Gmail API"}


@dataclass(frozen=True)
class Scope:
    key: str
    start: datetime
    end: datetime
    label: str
    provider: str = ""
    start_date: str = ""
    end_date: str = ""
    errors: tuple[str, ...] = field(default_factory=tuple)

    @property
    def bucket(self) -> str:
        return "hour" if self.end - self.start <= HOURLY_MAX_SPAN else "day"

    def params(self) -> dict[str, str]:
        """The query parameters that reproduce this scope, for links between the dashboard's pages."""
        values = {"range": self.key}
        if self.key == "custom":
            values.update(start=self.start_date, end=self.end_date)
        if self.provider:
            values["provider"] = self.provider
        return values

    def emails(self):
        rows = OutboundEmail.objects.filter(created_at__gte=self.start, created_at__lt=self.end)
        rows = rows.exclude(category=EmailCategory.ACCESS_CHECK)
        return rows.filter(provider=self.provider) if self.provider else rows

    def attempts(self):
        rows = OutboundEmailAttempt.objects.filter(started_at__gte=self.start, started_at__lt=self.end)
        rows = rows.exclude(email__category=EmailCategory.ACCESS_CHECK)
        return rows.filter(provider=self.provider) if self.provider else rows

    def bounces(self):
        return EmailBounce.objects.filter(received_at__gte=self.start, received_at__lt=self.end)


def _custom(params, now) -> Scope | str:
    try:
        start_day, end_day = parse_date(str(params.get("start") or "")), parse_date(str(params.get("end") or ""))
    except ValueError:  # well formed but not a date, such as 2026-02-30
        return "Enter real calendar dates for a custom range."
    if not isinstance(start_day, date) or not isinstance(end_day, date):
        return "Enter a start and an end date for a custom range."
    if end_day < start_day:
        return "The custom range ends before it starts."
    if (end_day - start_day).days >= MAX_CUSTOM_DAYS:
        return f"A custom range covers at most {MAX_CUSTOM_DAYS} days."
    try:
        start = timezone.make_aware(datetime.combine(start_day, time.min))
        end = min(timezone.make_aware(datetime.combine(end_day + timedelta(days=1), time.min)), now)
    except (OverflowError, ValueError):  # the last representable day, such as 9999-12-31
        return "Enter dates within the years the dashboard can show."
    label = f"{start_day:%b %d, %Y} – {end_day:%b %d, %Y}"
    return Scope(
        "custom", start, max(end, start), label, start_date=start_day.isoformat(), end_date=end_day.isoformat()
    )


def parse_scope(params, *, now: datetime | None = None) -> Scope:
    """The scope a request asks for; an invalid custom range falls back to the default preset, with the reason."""
    now = now or timezone.now()
    key = str(params.get("range") or DEFAULT_RANGE)
    provider = str(params.get("provider") or "")
    provider = provider if provider in PROVIDERS else ""
    errors: tuple[str, ...] = ()
    if key == "custom":
        custom = _custom(params, now)
        if isinstance(custom, Scope):
            return replace(custom, provider=provider)
        errors, key = (custom,), DEFAULT_RANGE
    if key not in PRESETS:
        key = DEFAULT_RANGE
    label, span = PRESETS[key]
    local_start = timezone.localdate(now - span)
    return Scope(
        key,
        now - span,
        now,
        label,
        provider=provider,
        start_date=local_start.isoformat(),
        end_date=timezone.localdate(now).isoformat(),
        errors=errors,
    )


def monitoring_began() -> datetime | None:
    """When the first outgoing email was recorded: nothing sent before it is shown, or reconstructed, anywhere."""
    return OutboundEmail.objects.order_by("created_at").values_list("created_at", flat=True).first()
