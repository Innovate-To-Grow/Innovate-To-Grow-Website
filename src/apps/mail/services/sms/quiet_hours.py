"""Quiet hours (Mail → SMS Settings): no Broadcast SMS or ticket text is sent inside the window.

The window is a local start and end time in one time zone (20:00–09:00 America/Los_Angeles by default). A start later
than the end spans midnight. Texts held by it wait for its end: queued campaign recipients and ticket texts are
scheduled then, a queued job that reaches the window is deferred to then (its attempt refunded), and the in-process
sender (background jobs off) pauses its remaining recipients. Sign-in and verification codes, which a person asks for
right now, and the admin's test SMS are never held.

``settings.SMS_QUIET_HOURS_ENFORCED`` is on in every deployment; the test settings turn it off so no test depends on
the time of day it runs.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone

from apps.mail.models import SmsConfig

HELD_LOG_MESSAGE = "Held for SMS quiet hours; it is sent when they end."
PAUSED_LOG_MESSAGE = "Paused for SMS quiet hours; send it with “Resume paused recipients” after they end."


@dataclass(frozen=True)
class QuietWindow:
    start: object
    end: object
    zone: object

    def contains(self, moment: datetime) -> bool:
        local = moment.astimezone(self.zone).time()
        if self.start < self.end:
            return self.start <= local < self.end
        return local >= self.start or local < self.end

    def ends_after(self, moment: datetime) -> datetime:
        """The end of the window ``moment`` falls in (``moment`` must be inside it)."""
        local = moment.astimezone(self.zone)
        end_date = local.date()
        if self.start > self.end and local.time() >= self.start:
            end_date += timedelta(days=1)
        # Built from the local wall time, so a daylight-saving change between now and then moves nothing.
        return datetime.combine(end_date, self.end, tzinfo=self.zone)

    def label(self) -> str:
        return f"{self.start:%H:%M}–{self.end:%H:%M} {self.zone.key}"


def quiet_window(config: SmsConfig | None = None) -> QuietWindow | None:
    """The window in force, or None when quiet hours are off (in SMS Settings, or for the deployment)."""
    if not getattr(settings, "SMS_QUIET_HOURS_ENFORCED", True):
        return None
    config = config or SmsConfig.load()
    if not config.quiet_hours_enabled or config.quiet_hours_start == config.quiet_hours_end:
        return None
    return QuietWindow(start=config.quiet_hours_start, end=config.quiet_hours_end, zone=config.zone)


def held_until(now: datetime | None = None, config: SmsConfig | None = None) -> datetime | None:
    """When a text may go out if ``now`` is inside quiet hours, else None."""
    now = now or timezone.now()
    window = quiet_window(config)
    if window is None or not window.contains(now):
        return None
    return window.ends_after(now)


def next_send_time(now: datetime | None = None, config: SmsConfig | None = None) -> datetime:
    """``now``, or the end of the quiet hours ``now`` falls in."""
    now = now or timezone.now()
    return held_until(now, config) or now
