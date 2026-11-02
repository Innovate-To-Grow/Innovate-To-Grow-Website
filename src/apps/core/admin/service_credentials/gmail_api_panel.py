"""The read-only Gmail API key panel, on the config page and on Mail → Notification Delivery.

It shows public facts only: the key id, service account, numeric client ID, project, where the key is stored and
when it was installed and checked, plus the allow-list with each account's verification. The key is never read to
build it. Key actions and the access check are superuser-only, so their links are offered to superusers only (the
views enforce the same rule).
"""

from django.urls import reverse

from apps.core.services.email.graph.credential.expiry import local_time_text

from .microsoft_graph_panel import STORE_NAMES

URL_NAME_PREFIX = "core_gmailapiproviderconfig"
INSTALL_URL_NAME = f"{URL_NAME_PREFIX}_install_key"
REMOVE_URL_NAME = f"{URL_NAME_PREFIX}_remove_key"
ACCESS_CHECK_URL_NAME = f"{URL_NAME_PREFIX}_run_access_check"


def _short(value: str, keep: int = 4) -> str:
    return f"{value[:keep]}…{value[-keep:]}" if len(value) > 2 * keep + 1 else value


def store_name(reference: str) -> str:
    return next((name for prefix, name in STORE_NAMES if reference.startswith(prefix)), "the credential store")


def key_panel(request, config, *, actions: bool = True) -> dict | None:
    """The panel's context for a saved config, or None for an unsaved one."""
    if config._state.adding:
        return None
    superuser = actions and request.user.is_superuser
    installed = config.key_configured
    subjects = [
        {"subject": row.subject, "verified": config.subject_verified(row.subject), "verified_at": row.verified_at}
        for row in config.subjects.all()
    ]
    panel = {
        "installed": installed,
        "subjects": subjects,
        "check_current": config.access_check_current,
        "installed_at": local_time_text(config.key_installed_at) if config.key_installed_at else "",
        "checked_at": local_time_text(config.access_checked_at) if config.access_checked_at else "",
        "install_url": reverse(f"admin:{INSTALL_URL_NAME}", args=[config.pk]) if superuser else "",
        "remove_url": reverse(f"admin:{REMOVE_URL_NAME}", args=[config.pk]) if superuser and installed else "",
        "access_check_url": reverse(f"admin:{ACCESS_CHECK_URL_NAME}", args=[config.pk]) if superuser else "",
    }
    if installed:
        panel.update(
            key_id=_short(config.key_id),
            service_account=config.service_account_email,
            client_id=config.client_id,
            project_id=config.project_id,
            store=store_name(config.key_secret_ref),
            version=_short(config.key_version_id, 6),
        )
    return panel
