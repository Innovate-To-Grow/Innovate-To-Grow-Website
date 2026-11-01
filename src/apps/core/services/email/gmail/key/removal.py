"""Remove the Gmail API key in an emergency (a leaked key, a service account being retired).

One transaction unpins the stored key, clears its facts and the access-check evidence, deactivates the config and,
when asked, switches email delivery to AWS SES (only when SES is ready). The stored version itself is not deleted:
the task role cannot delete secrets. It becomes useless once the key is deleted in Google Cloud, which the runbook
requires, together with removing the delegation in the Workspace Admin console.
"""

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.models import EmailServiceConfig, GmailApiProviderConfig, GmailApiSubject

from .install import KeyChangeError, record

NOTHING_TO_REMOVE = "No key is installed, so there is nothing to remove."


@dataclass(frozen=True)
class RemovalResult:
    key_id: str
    provider_switched: bool


def remove_key(config: GmailApiProviderConfig, *, reason: str, actor=None, switch_to_ses: bool = False):
    now = timezone.now()
    with transaction.atomic():
        locked = GmailApiProviderConfig.objects.select_for_update().get(pk=config.pk)
        if not locked.key_secret_ref and not locked.key_version_id:
            raise KeyChangeError(NOTHING_TO_REMOVE)
        key_id = locked.key_id
        GmailApiProviderConfig.objects.filter(pk=locked.pk).update(  # nosec B106 - clears the store pointer
            is_active=False,
            key_secret_ref="",
            key_version_id="",
            service_account_email="",
            client_id="",
            key_id="",
            project_id="",
            key_installed_at=None,
            access_checked_at=None,
            updated_at=now,
        )
        GmailApiSubject.objects.filter(config=locked).update(verified_at=None, updated_at=now)
        switched = switch_to_ses and _switch_to_ses()
        message = f"Gmail API key removed: key id {key_id or '-'}. Reason: {reason}"
        if switched:
            message = f"{message} Email delivery switched to AWS SES."
        record(actor, locked, message, action="removed", key_id=key_id)
    config.refresh_from_db()
    return RemovalResult(key_id=key_id, provider_switched=switched)


def _switch_to_ses() -> bool:
    email = EmailServiceConfig.objects.select_for_update().filter(is_active=True).first()
    if email is None or email.provider != EmailServiceConfig.Provider.GMAIL:
        return False
    email.provider = EmailServiceConfig.Provider.SES
    try:
        email.validate_activation()
    except ValidationError:
        return False
    email.save(update_fields=["provider", "updated_at"])
    return True
