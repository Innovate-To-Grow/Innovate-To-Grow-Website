"""How close a Microsoft Graph certificate is to expiry, against the thresholds in settings.

The admin's expiry badge, ``verify_service_configs`` and the background worker's hourly maintenance all use this,
so they agree: inside ``GRAPH_CERTIFICATE_EXPIRY_WARNING_DAYS`` the certificate needs renewing (amber badge,
warning, a fixed WARNING log line); inside ``GRAPH_CERTIFICATE_EXPIRY_CRITICAL_DAYS`` it is urgent (red badge, and
``verify_service_configs --strict`` fails while Graph is the selected provider).
"""

from dataclasses import dataclass

from django.conf import settings
from django.utils import timezone

from apps.core.models import MicrosoftGraphProviderConfig

NOT_YET_VALID, EXPIRED, CRITICAL, WARNING, OK = "not_yet_valid", "expired", "critical", "warning", "ok"


@dataclass(frozen=True)
class Expiry:
    level: str
    # Whole days until ``not_after`` (negative once expired).
    days_left: int


def certificate_expiry(certificate, *, now=None) -> Expiry:
    now = now or timezone.now()
    days_left = (certificate.not_after - now).days
    if certificate.not_before > now:
        level = NOT_YET_VALID
    elif certificate.not_after <= now:
        level = EXPIRED
    elif days_left <= settings.GRAPH_CERTIFICATE_EXPIRY_CRITICAL_DAYS:
        level = CRITICAL
    elif days_left <= settings.GRAPH_CERTIFICATE_EXPIRY_WARNING_DAYS:
        level = WARNING
    else:
        level = OK
    return Expiry(level, days_left)


def active_certificate_expiry(*, now=None) -> Expiry | None:
    """The expiry of the active Graph config's current certificate, or None when there is none."""
    certificate = MicrosoftGraphProviderConfig.load().current_certificate
    return None if certificate is None else certificate_expiry(certificate, now=now)


def local_time_text(value) -> str:
    """A date and time in the site's time zone, as the admin shows them, with the zone named."""
    return f"{timezone.localtime(value):%Y-%m-%d %H:%M %Z}"
