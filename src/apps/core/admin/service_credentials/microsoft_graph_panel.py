"""The read-only Microsoft Graph certificate panel, on the Graph config page and on Mail → Notification Delivery.

It shows public data only: thumbprints, subject, serial, validity and the key store version a certificate row pins,
then the latest access check and whether it is go-live evidence. The private key is never read to build it.
Core admins can install a certificate; rollback, removal and running the access check remain superuser-only.
The views enforce these permissions too. Dates are in the site's time zone, with the zone named.
"""

from django.conf import settings
from django.urls import reverse

from apps.core.models import MicrosoftGraphAccessCheck
from apps.core.models.base.service_credentials.microsoft_graph_access_check import go_live_problem
from apps.core.services.credential_store.local_file import LocalFileStore
from apps.core.services.credential_store.memory import MemoryStore
from apps.core.services.email.graph.credential import expiry
from apps.core.services.email.graph.credential.expiry import local_time_text
from apps.core.utils.access import user_can_access_app

URL_NAME_PREFIX = "core_microsoftgraphproviderconfig"
INSTALL_URL_NAME = f"{URL_NAME_PREFIX}_install_certificate"
ROLLBACK_URL_NAME = f"{URL_NAME_PREFIX}_rollback_certificate"
REMOVE_URL_NAME = f"{URL_NAME_PREFIX}_remove_certificates"
DOWNLOAD_URL_NAME = f"{URL_NAME_PREFIX}_download_certificate"
ACCESS_CHECK_URL_NAME = f"{URL_NAME_PREFIX}_run_access_check"
EVIDENCE_URL_NAME = "core_microsoftgraphaccesscheck_change"

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


EXPIRY_TONES = {
    expiry.NOT_YET_VALID: "danger",
    expiry.EXPIRED: "danger",
    expiry.CRITICAL: "danger",
    expiry.WARNING: "warning",
    expiry.OK: "success",
}
VERDICT_TONES = {
    MicrosoftGraphAccessCheck.Verdict.COMPLIANT: "success",
    MicrosoftGraphAccessCheck.Verdict.INCOMPLETE: "warning",
    MicrosoftGraphAccessCheck.Verdict.NOT_COMPLIANT: "danger",
}


def expiry_badge(certificate, *, now=None) -> tuple[str, str]:
    """``(label, tone)`` for a certificate's validity; the day thresholds come from settings (``expiry``)."""
    status = expiry.certificate_expiry(certificate, now=now)
    if status.level == expiry.NOT_YET_VALID:
        return "Not valid yet", "danger"
    if status.level == expiry.EXPIRED:
        return "Expired", "danger"
    days = status.days_left
    label = "Expires within a day" if days == 0 else f"Expires in {days} day{'' if days == 1 else 's'}"
    return label, EXPIRY_TONES[status.level]


def store_name(store_arn: str) -> str:
    for prefix, name in STORE_NAMES:
        if store_arn.startswith(prefix):
            return name
    return "the credential store"


def certificate_card(certificate) -> dict | None:
    if certificate is None:
        return None
    label, tone = expiry_badge(certificate)
    code = f" ({certificate.entra_check_code})" if certificate.entra_check_code else ""
    return {
        "certificate": certificate,
        "valid_from": local_time_text(certificate.not_before),
        "valid_until": local_time_text(certificate.not_after),
        "expiry_label": label,
        "expiry_tone": tone,
        "badge_classes": BADGE_CLASSES[tone],
        "store": store_name(certificate.store_arn),
        "entra_check": f"{certificate.get_entra_check_display()}{code}, {local_time_text(certificate.entra_checked_at)}",
    }


def access_check_card(config, current, *, linked: bool) -> dict:
    """The latest access check of *config* and whether email may switch to Graph on it (the go-live gate)."""
    check = config.access_checks.order_by("-created_at").first()
    card = {
        "check": check,
        "gate_enforced": settings.GRAPH_REQUIRE_ACCESS_EVIDENCE,
        "gate_problem": go_live_problem(config),
        "deny_mailbox": config.access_check_deny_mailbox,
        "exception_reference": config.permission_exception_reference,
    }
    if check is None:
        return card
    granted = check.granted_roles
    card.update(
        checked=local_time_text(check.created_at),
        for_current=current is not None and check.certificate_id == current.pk,
        badge_classes=BADGE_CLASSES[VERDICT_TONES[check.verdict]],
        roles="unreadable" if granted is None else (", ".join(granted) or "none in the token"),
    )
    if linked:
        card["url"] = reverse(f"admin:{EVIDENCE_URL_NAME}", args=[check.pk])
    return card


def certificate_panel(request, config, *, actions=True) -> dict:
    """Template context for ``certificate_panel.html``. ``actions=False`` leaves out the certificate actions and the
    "Run access check" button."""
    saved = config is not None and not config._state.adding
    current = config.current_certificate if saved else None
    previous = config.previous_certificate if saved else None
    panel = {"config": config, "current": certificate_card(current), "previous": certificate_card(previous)}
    if not saved:
        return panel
    core_staff = user_can_access_app(request.user, "core")
    panel["access_check"] = access_check_card(config, current, linked=core_staff)
    if not core_staff:
        return panel
    args = [config.pk]
    if current is not None:
        panel["download_url"] = reverse(f"admin:{DOWNLOAD_URL_NAME}", args=args)
    if actions:
        panel["install_url"] = reverse(f"admin:{INSTALL_URL_NAME}", args=args)
    if actions and request.user.is_superuser:
        panel["access_check_url"] = reverse(f"admin:{ACCESS_CHECK_URL_NAME}", args=args)
        if previous is not None:
            panel["rollback_url"] = reverse(f"admin:{ROLLBACK_URL_NAME}", args=args)
        if current is not None or previous is not None:
            panel["remove_url"] = reverse(f"admin:{REMOVE_URL_NAME}", args=args)
    return panel
