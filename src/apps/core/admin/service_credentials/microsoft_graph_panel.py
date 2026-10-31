"""The read-only Microsoft Graph certificate panel, on the Graph config page and on Mail → Notification Delivery.

It shows public data only: thumbprints, subject, serial, validity and the key store version a certificate row pins.
The private key is never read to build it. Certificate actions (install, roll back, remove) are superuser-only, so
their links are offered to superusers only; the views enforce the same rule.
"""

import datetime

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from apps.core.services.credential_store.local_file import LocalFileStore
from apps.core.services.credential_store.memory import MemoryStore
from apps.core.utils.access import user_can_access_app

URL_NAME_PREFIX = "core_microsoftgraphproviderconfig"
INSTALL_URL_NAME = f"{URL_NAME_PREFIX}_install_certificate"
ROLLBACK_URL_NAME = f"{URL_NAME_PREFIX}_rollback_certificate"
REMOVE_URL_NAME = f"{URL_NAME_PREFIX}_remove_certificates"
DOWNLOAD_URL_NAME = f"{URL_NAME_PREFIX}_download_certificate"

STORE_NAMES = (
    ("arn:aws:secretsmanager:", "AWS Secrets Manager"),
    (f"{LocalFileStore.scheme}:", "the local file store (development only)"),
    (f"{MemoryStore.scheme}:", "the in-memory store (tests only)"),
)
BADGE_CLASSES = {
    "success": "bg-green-50 text-green-700 ring-green-600/20 dark:bg-green-900/30 dark:text-green-400",
    "warning": "bg-yellow-50 text-yellow-700 ring-yellow-600/20 dark:bg-yellow-900/30 dark:text-yellow-400",
    "danger": "bg-red-50 text-red-700 ring-red-600/20 dark:bg-red-900/30 dark:text-red-400",
}


def expiry_badge(certificate, *, now=None) -> tuple[str, str]:
    """``(label, tone)`` for a certificate's validity; the day thresholds come from settings."""
    now = now or timezone.now()
    if certificate.not_before > now:
        return "Not valid yet", "danger"
    if certificate.not_after <= now:
        return "Expired", "danger"
    days = (certificate.not_after - now).days
    label = "Expires within a day" if days == 0 else f"Expires in {days} day{'' if days == 1 else 's'}"
    if days <= settings.GRAPH_CERTIFICATE_EXPIRY_CRITICAL_DAYS:
        return label, "danger"
    if days <= settings.GRAPH_CERTIFICATE_EXPIRY_WARNING_DAYS:
        return label, "warning"
    return label, "success"


def store_name(store_arn: str) -> str:
    for prefix, name in STORE_NAMES:
        if store_arn.startswith(prefix):
            return name
    return "the credential store"


def utc_text(value) -> str:
    return f"{value.astimezone(datetime.UTC):%Y-%m-%d %H:%M} UTC"


def certificate_card(certificate) -> dict | None:
    if certificate is None:
        return None
    label, tone = expiry_badge(certificate)
    code = f" ({certificate.entra_check_code})" if certificate.entra_check_code else ""
    return {
        "certificate": certificate,
        "valid_from": utc_text(certificate.not_before),
        "valid_until": utc_text(certificate.not_after),
        "expiry_label": label,
        "expiry_tone": tone,
        "badge_classes": BADGE_CLASSES[tone],
        "store": store_name(certificate.store_arn),
        "entra_check": f"{certificate.get_entra_check_display()}{code}, {utc_text(certificate.entra_checked_at)}",
    }


def certificate_panel(request, config, *, actions=True) -> dict:
    """Template context for ``certificate_panel.html``. ``actions=False`` leaves out the certificate actions."""
    saved = config is not None and not config._state.adding
    current = config.current_certificate if saved else None
    previous = config.previous_certificate if saved else None
    panel = {"config": config, "current": certificate_card(current), "previous": certificate_card(previous)}
    if not saved or not user_can_access_app(request.user, "core"):
        return panel
    args = [config.pk]
    if current is not None:
        panel["download_url"] = reverse(f"admin:{DOWNLOAD_URL_NAME}", args=args)
    if actions and request.user.is_superuser:
        panel["install_url"] = reverse(f"admin:{INSTALL_URL_NAME}", args=args)
        if previous is not None:
            panel["rollback_url"] = reverse(f"admin:{ROLLBACK_URL_NAME}", args=args)
        if current is not None or previous is not None:
            panel["remove_url"] = reverse(f"admin:{REMOVE_URL_NAME}", args=args)
    return panel
