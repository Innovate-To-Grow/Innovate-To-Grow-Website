"""Install a Microsoft Graph certificate. The certificate it replaces is kept as previous, for rollback.

Order of every change: validate in memory (``parsing``) -> test with Microsoft Entra -> write the private key to the
credential store, outside any database transaction -> pin the stored version in one short transaction -> move the
store's AWSCURRENT label after commit, best effort. The database pin is authoritative: a stored version no row pins
is never read, so a failure after the store write leaves the site exactly as it was.
"""

import dataclasses
import logging
from functools import partial

from django.contrib.admin.models import CHANGE, LogEntry
from django.db import transaction
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables

from apps.core.models import MicrosoftGraphCertificate, MicrosoftGraphProviderConfig
from apps.core.services.credential_store import CredentialStoreError, StoredVersion, get_store
from apps.core.utils.security import is_entra_tenant, is_guid

from . import entra_check, stored_key
from .parsing import PRIVATE_KEY, ParsedCertificate

logger = logging.getLogger(__name__)
State = MicrosoftGraphCertificate.State

APPLICATION_REQUIRED = "Save a valid tenant ID and client ID before installing a certificate."
ALREADY_CURRENT = "This certificate is already the current certificate."
IS_PREVIOUS = "This is the previous certificate: roll back to it instead of installing it again."
NO_KEY_TO_REUSE = "Enter the private key: no installed certificate has this certificate's key."
KEY_REQUIRED = "Enter the private key: this certificate has a different key than the installed one."
ACTIVE_NEEDS_TRUST = (
    "This config is sending mail, so a certificate Entra does not accept would stop email. "
    "Ask OIT to register it on the app first. Nothing was changed."
)
APPLICATION_CHANGED = "The Entra application changed while the certificate was being tested. Nothing was changed."
REPLACED_NOTE = "Replaced by a newer certificate."


class CertificateChangeError(ValueError):
    """A certificate change was refused or failed before anything was pinned. Fixed text, never key material."""

    def __init__(self, message: str, *, field: str | None = None):
        super().__init__(message)
        self.field = field
        self.message = message


@sensitive_variables()
def install_certificate(config, parsed: ParsedCertificate, *, actor=None) -> MicrosoftGraphCertificate:
    """Test, store and pin *parsed* as the current certificate of *config* (a saved config).

    A certificate without a private key re-issues the installed key: its public key must equal the current
    certificate's, and the stored version is reused instead of writing a new one.
    """
    if config._state.adding or not (is_entra_tenant(config.tenant_id) and is_guid(config.client_id)):
        raise CertificateChangeError(APPLICATION_REQUIRED)
    _refuse_duplicate(config, parsed.facts)
    private_key, reused = _signing_key(config, parsed)
    check = entra_check.check_certificate(
        tenant_id=config.tenant_id, client_id=config.client_id, private_key=private_key, x5t_s256=parsed.facts.x5t_s256
    )
    _refuse_failed_check(config, check)
    stored = reused or _store(private_key)
    return _pin(config, parsed.facts, stored, check, actor)


@sensitive_variables()
def read_pinned_key(certificate: MicrosoftGraphCertificate):
    """The private key a certificate row pins, as a ``CertificateChangeError`` on any store failure."""
    try:
        return stored_key.read_key(
            arn=certificate.store_arn,
            version_id=certificate.store_version_id,
            expected_public_key_sha256=certificate.public_key_sha256,
        )
    except CredentialStoreError as exc:
        error = CertificateChangeError(f"The installed private key could not be read. Nothing was changed. {exc}")
    raise error


def lock_config(config) -> MicrosoftGraphProviderConfig:
    return MicrosoftGraphProviderConfig.objects.select_for_update().get(pk=config.pk)


def record(actor, config, message: str, *, action: str, certificate: MicrosoftGraphCertificate | None) -> None:
    """Admin history (LogEntry) plus one log line; both carry only public identifiers."""
    logger.info(
        "graph_certificate_event action=%s sha1=%s version=%s config=%s actor=%s",
        action,
        certificate.sha1_thumbprint if certificate else "-",
        certificate.store_version_id if certificate else "-",
        config.pk,
        getattr(actor, "pk", None) or "-",
    )
    if getattr(actor, "pk", None):
        LogEntry.objects.log_actions(
            user_id=actor.pk, queryset=[config], action_flag=CHANGE, change_message=message, single_object=True
        )


def summary(certificate: MicrosoftGraphCertificate) -> str:
    return (
        f"SHA-1 {certificate.sha1_thumbprint}, valid until {certificate.not_after:%Y-%m-%d}, "
        f"key version {certificate.store_version_id}"
    )


def relabel_after_commit(config, certificate: MicrosoftGraphCertificate) -> None:
    """Once the pin commits, label the pinned version AWSCURRENT (bookkeeping only; the pin decides)."""
    if config.is_active:
        transaction.on_commit(partial(_relabel, certificate.store_version_id))


def _refuse_duplicate(config, facts) -> None:
    for certificate, message in (
        (config.current_certificate, ALREADY_CURRENT),
        (config.previous_certificate, IS_PREVIOUS),
    ):
        if certificate is not None and certificate.sha256_fingerprint == facts.sha256_fingerprint:
            raise CertificateChangeError(message)


@sensitive_variables()
def _signing_key(config, parsed: ParsedCertificate):
    if parsed.private_key is not None:
        return parsed.private_key, None
    current = config.current_certificate
    if current is None:
        raise CertificateChangeError(NO_KEY_TO_REUSE, field=PRIVATE_KEY)
    if current.public_key_sha256 != parsed.facts.public_key_sha256:
        raise CertificateChangeError(KEY_REQUIRED, field=PRIVATE_KEY)
    return read_pinned_key(current), StoredVersion(arn=current.store_arn, version_id=current.store_version_id)


def _refuse_failed_check(config, check) -> None:
    if check.refuses_change:
        raise CertificateChangeError(f"{check.describe()} Nothing was changed.")
    if config.is_active and not check.accepted:
        raise CertificateChangeError(f"{check.describe()} {ACTIVE_NEEDS_TRUST}")


@sensitive_variables()
def _store(private_key) -> StoredVersion:
    try:
        return stored_key.store_key(private_key)
    except CredentialStoreError as exc:
        error = CertificateChangeError(f"The private key could not be stored. Nothing was changed. {exc}")
    raise error


def _pin(config, facts, stored: StoredVersion, check, actor) -> MicrosoftGraphCertificate:
    now = timezone.now()
    with transaction.atomic():
        locked = lock_config(config)
        if (locked.tenant_id, locked.client_id) != (config.tenant_id, config.client_id):
            raise CertificateChangeError(APPLICATION_CHANGED)
        _refuse_failed_check(locked, check)
        rows = MicrosoftGraphCertificate.objects.filter(config=locked)
        rows.filter(state=State.PREVIOUS).update(
            state=State.REMOVED, removed_at=now, removal_note=REPLACED_NOTE, updated_at=now
        )
        rows.filter(state=State.CURRENT).update(state=State.PREVIOUS, updated_at=now)
        certificate = MicrosoftGraphCertificate.objects.create(
            config=locked,
            state=State.CURRENT,
            tenant_id=locked.tenant_id,
            client_id=locked.client_id,
            store_arn=stored.arn,
            store_version_id=stored.version_id,
            entra_check=check.outcome,
            entra_check_code=check.code,
            entra_checked_at=now,
            **dataclasses.asdict(facts),
        )
        message = f"Installed Microsoft Graph certificate ({summary(certificate)}). {check.describe()}"
        record(actor, locked, message, action="installed", certificate=certificate)
        relabel_after_commit(locked, certificate)
    return certificate


def _relabel(version_id: str) -> None:
    try:
        get_store().move_current(stored_key.KEY_NAME, version_id)
    except CredentialStoreError as exc:
        logger.warning("Microsoft Graph key version could not be labelled current: %s", exc.code or "refused")
