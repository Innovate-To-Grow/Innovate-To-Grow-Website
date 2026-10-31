"""System checks for settings that must hold before the site starts.

Every management command runs them, including the startup commands in ``entrypoint.sh`` and the background worker,
so a production task whose key store is not Secrets Manager stops before it serves a request.
"""

from django.conf import settings
from django.core.checks import Error, Tags, register

from .services.credential_store import BACKENDS, SECRETS_MANAGER, valid_secret_id, valid_staged_label

_POSITIVE_NUMBER_SETTINGS = (
    "CREDENTIAL_STORE_CONNECT_TIMEOUT_SECONDS",
    "CREDENTIAL_STORE_READ_TIMEOUT_SECONDS",
    "CREDENTIAL_STORE_TOTAL_MAX_ATTEMPTS",
    "CREDENTIAL_STORE_MAX_PAYLOAD_BYTES",
    "GRAPH_CERTIFICATE_MIN_RSA_KEY_BITS",
    "GRAPH_CERTIFICATE_MAX_INPUT_BYTES",
    "GRAPH_CERTIFICATE_CHECK_TIMEOUT_SECONDS",
)


def _backend_errors() -> list[Error]:
    errors = []
    backend = getattr(settings, "CREDENTIAL_STORE_BACKEND", "")
    if backend not in BACKENDS:
        errors.append(Error(f"CREDENTIAL_STORE_BACKEND must be one of: {', '.join(BACKENDS)}.", id="core.E001"))
    if getattr(settings, "CREDENTIAL_STORE_REQUIRE_SECRETS_MANAGER", False) and backend != SECRETS_MANAGER:
        errors.append(
            Error(
                f"This environment requires CREDENTIAL_STORE_BACKEND = {SECRETS_MANAGER!r}.",
                hint="Private keys may live only in AWS Secrets Manager here; the local file and memory stores "
                "are for development and tests.",
                id="core.E002",
            )
        )
    return errors


def _secret_errors() -> list[Error]:
    errors = []
    secrets = getattr(settings, "CREDENTIAL_STORE_SECRETS", None)
    if isinstance(secrets, dict):
        invalid = sorted(str(name) for name, secret_id in secrets.items() if not valid_secret_id(secret_id))
    else:
        invalid = ["(the setting is not a dict)"]
    if invalid:
        errors.append(
            Error(
                f"CREDENTIAL_STORE_SECRETS has an invalid secret name for: {', '.join(invalid)}.",
                hint="Use a Secrets Manager secret name outside the itg/backend/aws-credentials/ namespace.",
                id="core.E003",
            )
        )
    if not valid_staged_label(getattr(settings, "CREDENTIAL_STORE_STAGED_LABEL", None)):
        errors.append(
            Error("CREDENTIAL_STORE_STAGED_LABEL must be a staging label not starting with AWS.", id="core.E004")
        )
    for name in _POSITIVE_NUMBER_SETTINGS:
        value = getattr(settings, name, None)
        if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
            errors.append(Error(f"{name} must be a positive number.", id="core.E005"))
    return errors


@register(Tags.security)
def check_credential_store(app_configs=None, **kwargs):
    return _backend_errors() + _secret_errors()
