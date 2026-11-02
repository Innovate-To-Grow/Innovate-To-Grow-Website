"""Roll back to the previous Microsoft Graph certificate, or remove the installed ones in an emergency.

Rollback swaps current and previous only after Entra issues a token with the previous key. Remove clears the pin:
both rows become removed, so every process refuses to sign at its next token request without any store or Entra
call. The stored key versions and their labels are left alone; what stops new tokens is OIT removing the
certificate from the Entra app (or disabling the service principal).
"""

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables

from apps.core.models import EmailServiceConfig, MicrosoftGraphCertificate

from .. import auth
from . import entra_check
from .lifecycle import CertificateChangeError, lock_config, read_pinned_key, record, relabel_after_commit, summary

State = MicrosoftGraphCertificate.State

NO_PREVIOUS = "There is no previous certificate to roll back to."
PREVIOUS_NOT_VALID = "The previous certificate is expired or not valid yet, so it cannot be used again."
PREVIOUS_OTHER_APPLICATION = "The previous certificate was tested for another Entra application."
CHANGED_MEANWHILE = "The installed certificates changed meanwhile. Nothing was changed; reload and try again."
REASON_REQUIRED = "Give a reason for removing the certificates."
REASON_FIELD = "reason"


@dataclass(frozen=True)
class RemovalResult:
    removed: int
    provider_switched: bool


@sensitive_variables()
def rollback_certificate(config, *, actor=None) -> MicrosoftGraphCertificate:
    """Make the previous certificate current again (and the current one previous). Raises ``CertificateChangeError``."""
    previous = config.previous_certificate
    if previous is None:
        raise CertificateChangeError(NO_PREVIOUS)
    if not previous.valid_now():
        raise CertificateChangeError(PREVIOUS_NOT_VALID)
    if (previous.tenant_id, previous.client_id) != (config.tenant_id, config.client_id):
        raise CertificateChangeError(PREVIOUS_OTHER_APPLICATION)
    current = config.current_certificate
    check = entra_check.check_certificate(
        tenant_id=config.tenant_id,
        client_id=config.client_id,
        private_key=read_pinned_key(previous),
        x5t_s256=previous.x5t_s256,
    )
    if not check.accepted:
        raise CertificateChangeError(f"{check.describe()} The previous certificate was not restored.")
    return _swap(config, previous, current, check, actor)


def remove_certificates(config, *, reason: str, actor=None, switch_to_ses: bool = False) -> RemovalResult:
    """Emergency: unpin the current and previous certificates; optionally move the active provider to SES."""
    reason = " ".join(str(reason or "").split())
    if not reason:
        raise CertificateChangeError(REASON_REQUIRED, field=REASON_FIELD)
    now = timezone.now()
    note_length = MicrosoftGraphCertificate.removal_note.field.max_length
    with transaction.atomic():
        locked = lock_config(config)
        live = MicrosoftGraphCertificate.objects.filter(config=locked, state__in=MicrosoftGraphCertificate.LIVE_STATES)
        removed = live.update(state=State.REMOVED, removed_at=now, removal_note=reason[:note_length], updated_at=now)
        switched = switch_to_ses and locked.is_active and _switch_provider_to_ses()
        provider_note = " Email provider switched to AWS SES." if switched else ""
        message = f"Removed {removed} Microsoft Graph certificate(s). Reason: {reason}{provider_note}"
        record(actor, locked, message, action="removed", certificate=None)
        transaction.on_commit(auth.clear_access_token_cache)
    return RemovalResult(removed=removed, provider_switched=bool(switched))


def _swap(config, previous, current, check, actor) -> MicrosoftGraphCertificate:
    now = timezone.now()
    with transaction.atomic():
        locked = lock_config(config)
        rows = MicrosoftGraphCertificate.objects.filter(config=locked)
        if locked.previous_certificate != previous or locked.current_certificate != current:
            raise CertificateChangeError(CHANGED_MEANWHILE)
        # One state per statement keeps the one-current / one-previous constraints satisfied at every step.
        if current is not None:
            rows.filter(pk=current.pk).update(state=State.REMOVED, updated_at=now)
        rows.filter(pk=previous.pk).update(
            state=State.CURRENT,
            entra_check=check.outcome,
            entra_check_code=check.code,
            entra_checked_at=now,
            updated_at=now,
        )
        if current is not None:
            rows.filter(pk=current.pk).update(state=State.PREVIOUS, updated_at=now)
        restored = rows.get(pk=previous.pk)
        record(
            actor,
            locked,
            f"Rolled back to Microsoft Graph certificate ({summary(restored)}).",
            action="rolled_back",
            certificate=restored,
        )
        relabel_after_commit(locked, restored)
    return restored


def _switch_provider_to_ses() -> bool:
    """Move the active email config from Graph to SES when SES is ready; otherwise leave it (and say so)."""
    email = EmailServiceConfig.load()
    if not email.pk or email.provider != EmailServiceConfig.Provider.GRAPH:
        return False
    email.provider = EmailServiceConfig.Provider.SES
    try:
        with transaction.atomic():
            email.validate_activation()
            email.save(update_fields=["provider", "updated_at"])
    except ValidationError:
        return False
    return True
