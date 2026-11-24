"""AI provider API keys in the credential store (AWS Secrets Manager in production, a 0600 file locally).

One logical secret holds every provider's key, one immutable version per installed key: the payload is
``{"provider_id", "api_key"}`` and the provider row pins the version it uses. A read names that exact version and
must return the row's own id, so a pin copied to another row is refused. Nothing caches a key and no key is ever put
in ``os.environ`` (LiteLLM would read it as a process-wide default).

Known limit: each install adds a version under the staged label, which leaves earlier pinned versions unlabelled.
Secrets Manager may delete unlabelled versions once a secret holds about 100 versions, so after very many installs
an older provider's pin can stop resolving (``UNREADABLE``); installing that provider's key again repairs it.
"""

import hashlib

from django.utils import timezone
from django.views.decorators.debug import sensitive_variables

from apps.core.services.credential_store import CredentialStoreError, get_store, version_token_for

KEY_NAME = "system_intelligence_llm_api_key"
MIN_KEY_CHARS = 8
MAX_KEY_CHARS = 512
KEY_FORMAT = f"An API key is {MIN_KEY_CHARS}-{MAX_KEY_CHARS} printable characters without spaces."
NOT_INSTALLED = "This AI provider has no API key installed."
MISMATCH = "The stored API key does not belong to this AI provider. Install the key again."
UNREADABLE = "The AI provider's API key could not be read from the credential store."


class ProviderKeyError(Exception):
    """An API key could not be installed or read. The message is fixed text and never contains the key."""


@sensitive_variables()
def validate_api_key(api_key) -> str:
    key = api_key.strip() if isinstance(api_key, str) else ""
    printable = all(33 <= ord(char) <= 126 for char in key)
    if not (MIN_KEY_CHARS <= len(key) <= MAX_KEY_CHARS) or not printable:
        raise ProviderKeyError(KEY_FORMAT)
    return key


@sensitive_variables()
def install_api_key(provider, api_key) -> None:
    """Store *api_key* as a new version and pin it on *provider* (which must be saved)."""
    key = validate_api_key(api_key)
    fingerprint = hashlib.sha256(f"{provider.pk}:{key}".encode()).hexdigest()
    try:
        stored = get_store().put(
            KEY_NAME,
            {"provider_id": str(provider.pk), "api_key": key},
            version_token=version_token_for(KEY_NAME, fingerprint),
        )
    except CredentialStoreError as exc:
        raise ProviderKeyError(f"The API key could not be stored: {exc}") from None
    provider.key_secret_ref = stored.arn
    provider.key_version_id = stored.version_id
    provider.key_hint = key[-4:]
    provider.key_installed_at = timezone.now()
    provider.save(update_fields=["key_secret_ref", "key_version_id", "key_hint", "key_installed_at", "updated_at"])


def remove_api_key(provider) -> None:
    """Unpin the key and disable the provider. The stored version stays in the store, unlabelled."""
    provider.key_secret_ref = ""  # nosec B105 - clears a store pointer, not a password
    provider.key_version_id = ""
    provider.key_hint = ""
    provider.key_installed_at = None
    provider.is_enabled = False
    provider.save(
        update_fields=["key_secret_ref", "key_version_id", "key_hint", "key_installed_at", "is_enabled", "updated_at"]
    )


@sensitive_variables()
def read_api_key(provider) -> str:
    if not provider.key_configured:
        raise ProviderKeyError(NOT_INSTALLED)
    try:
        payload = get_store().read(KEY_NAME, arn=provider.key_secret_ref, version_id=provider.key_version_id)
    except CredentialStoreError:
        raise ProviderKeyError(UNREADABLE) from None
    key = payload.get("api_key")
    if payload.get("provider_id") != str(provider.pk) or not isinstance(key, str) or not key.strip():
        raise ProviderKeyError(MISMATCH)
    return key.strip()
