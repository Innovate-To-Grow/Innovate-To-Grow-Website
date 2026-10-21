"""The Amplify deployment configuration a reconciliation runs with.

Each queued job carries a snapshot of these settings, and the newest snapshot any job
carries wins, so an older task in a rolling deployment never reverts a newer one.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from django.conf import settings

from .errors import AmplifyRedirectConfigurationError

AMPLIFY_REDIRECT_JOB_KIND = "cms.amplify_redirects"
AMPLIFY_CONFIGURATION_PAYLOAD_KEY = "amplify_configuration"


def _configured_app_id() -> str:
    return str(getattr(settings, "AMPLIFY_APP_ID", "") or "").strip()


def _configured_region() -> str:
    return str(
        getattr(settings, "AWS_REGION", "") or getattr(settings, "AWS_S3_REGION_NAME", "") or "us-west-2"
    ).strip()


def _configured_proxy_admin_paths() -> bool:
    value = getattr(settings, "AMPLIFY_PROXY_ADMIN_PATHS", False)
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _configured_amplify_configuration() -> dict[str, Any]:
    """Capture the provider/base-rule settings that one queued revision owns.

    Jobs carry this snapshot so any compatible worker can execute them during
    an ECS rolling deployment without substituting that worker's older
    environment values.
    """

    return {
        "config_revision": str(getattr(settings, "AMPLIFY_CONFIG_REVISION", "0") or "0").strip() or "0",
        "app_id": _configured_app_id(),
        "region": _configured_region(),
        "backend_proxy_url": str(getattr(settings, "AMPLIFY_BACKEND_PROXY_URL", "") or "").strip().rstrip("/"),
        "proxy_admin_paths": _configured_proxy_admin_paths(),
    }


def _configuration_revision_key(configuration: dict[str, Any] | None) -> tuple[int, ...]:
    """Return a numerically comparable deployment generation.

    Production injects ``github.run_id.github.run_attempt``. Missing or
    malformed values are treated as generation zero for compatibility with
    jobs queued before this field existed.
    """

    if not isinstance(configuration, dict):
        return (0,)
    value = str(configuration.get("config_revision") or "0").strip()
    components = value.split(".")
    if not components or any(not component.isdigit() for component in components):
        return (0,)
    return tuple(int(component) for component in components)


def _latest_known_amplify_configuration(background_job_model) -> dict[str, Any]:
    """Keep an older rolling task from replacing a newer shared config.

    Amplify jobs are durable and retained, so their snapshots also form the
    shared generation ledger. The scheduler lock serializes selection and
    update of this ledger. A route edit produced by an older web task still
    queues a reconciliation, but carries forward the newest known snapshot.
    """

    configured = _configured_amplify_configuration()
    selected = configured
    selected_key = _configuration_revision_key(configured)
    payloads = (
        background_job_model.objects.filter(kind=AMPLIFY_REDIRECT_JOB_KIND)
        .order_by("-created_at")
        .values_list("payload", flat=True)
    )
    for payload in payloads:
        candidate = (payload or {}).get(AMPLIFY_CONFIGURATION_PAYLOAD_KEY)
        candidate_key = _configuration_revision_key(candidate)
        if isinstance(candidate, dict) and candidate_key > selected_key:
            selected = dict(candidate)
            selected_key = candidate_key
    return selected


def _resolved_amplify_configuration(configuration: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = _configured_amplify_configuration() if configuration is None else configuration
    if not isinstance(raw, dict):
        raise AmplifyRedirectConfigurationError("Amplify reconciliation configuration is invalid.")

    app_id = str(raw.get("app_id") or "").strip()
    if not app_id:
        raise AmplifyRedirectConfigurationError("AMPLIFY_APP_ID is not configured.")

    region = str(raw.get("region") or "us-west-2").strip() or "us-west-2"
    backend_proxy_url = str(raw.get("backend_proxy_url") or "").strip().rstrip("/")
    parsed = urlsplit(backend_proxy_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment:
        raise AmplifyRedirectConfigurationError(
            "AMPLIFY_BACKEND_PROXY_URL must be an absolute HTTP(S) URL without query or fragment."
        )

    proxy_admin_paths = raw.get("proxy_admin_paths", False)
    if not isinstance(proxy_admin_paths, bool):
        proxy_admin_paths = str(proxy_admin_paths or "").strip().lower() in {"1", "true", "yes", "on"}

    return {
        "app_id": app_id,
        "region": region,
        "backend_proxy_url": backend_proxy_url,
        "proxy_admin_paths": proxy_admin_paths,
    }
