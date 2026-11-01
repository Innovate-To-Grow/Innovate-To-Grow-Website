"""Install a Gmail API service-account key: test it with Google, store it, then pin it.

Order: check the file in memory (``parsing``) -> ask Google for a gmail.send token as the From address -> write the
key to the credential store, outside any database transaction -> pin the stored version and record the public facts
in one short transaction -> label the version AWSCURRENT after commit, best effort. The pin is authoritative: a
stored version no row pins is never read, so a failure after the store write leaves the site as it was.

What the token test must show depends on what the key replaces:

- a new key for the same service account (rotation), a key for another service account while email is sent
  through the Gmail API, or any key for an active config: Google must issue a token, or nothing is written;
- otherwise (a first install, an inactive config): a token, or ``unauthorized_client`` / ``access_denied`` (the
  Workspace admin may still be authorizing the client ID, "up to 24 hours"). Any other refusal writes nothing.

Every successful install clears the access-check evidence, so activation needs the access check again.
"""

import logging
from dataclasses import dataclass
from functools import partial

from django.conf import settings
from django.contrib.admin.models import CHANGE, LogEntry
from django.db import transaction
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables

from apps.core.models import EmailServiceConfig, GmailApiProviderConfig, GmailApiSubject
from apps.core.models.base.delivery_rates import DeliveryChannel
from apps.core.services.credential_store import CredentialStoreError, get_store
from apps.core.services.delivery_rates import receivers

from ...exceptions import EmailDeliveryError, TransientEmailDeliveryError
from .. import auth
from ..access import GmailScopeError, require_subject
from ..errors import DELEGATION_PENDING_CODES, GmailTokenRefused
from . import stored_key
from .parsing import ParsedKey

logger = logging.getLogger(__name__)

ISSUED = "issued"
PENDING = "pending"
REFUSED = "refused"
UNREACHABLE = "unreachable"

SAVE_FIRST = "Save the configuration before installing a key."
FROM_NOT_LISTED = (
    "Add the From address ({address}) to the account allow-list first: the key is tested with a gmail.send token "
    "for it."
)
NEEDS_TOKEN = (  # nosec B105 - a validation message
    "{reason}, so the key must already work: Google did not issue a token ({result}). Nothing was changed."
)
NOT_ACCEPTED = "Google did not accept the key ({result}). Nothing was changed."
CHANGED_MEANWHILE = "The configuration changed while the key was being tested. Nothing was changed."
STORE_FAILED = "The key could not be stored. Nothing was changed. {error}"


class KeyChangeError(ValueError):
    """A key change was refused or failed before anything was pinned. Fixed text, never key material."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class TokenTest:
    outcome: str
    detail: str = ""

    def describe(self) -> str:
        if self.outcome == ISSUED:
            return "Google issued a gmail.send token with this key."
        if self.outcome == PENDING:
            return f"Delegation is not authorized yet: {self.detail} Run the access check once it is."
        return self.detail


@sensitive_variables()
def check_key(parsed: ParsedKey, subject) -> TokenTest:
    """One gmail.send token request with the in-memory key. Nothing is cached, stored or sent."""
    credential = auth.GmailCredential(parsed.client_email, parsed.client_id, parsed.key_id, "", "")
    timeout = settings.GMAIL_API["key_check_timeout_seconds"]
    try:
        auth.request_token(credential, parsed.private_key, subject, timeout=timeout)
    except GmailTokenRefused as exc:
        return TokenTest(PENDING if exc.code in DELEGATION_PENDING_CODES else REFUSED, str(exc))
    except TransientEmailDeliveryError as exc:
        return TokenTest(UNREACHABLE, str(exc))
    except EmailDeliveryError as exc:
        return TokenTest(REFUSED, str(exc))
    return TokenTest(ISSUED)


@sensitive_variables()
def install_key(config: GmailApiProviderConfig, parsed: ParsedKey, *, actor=None) -> TokenTest:
    """Test, store and pin *parsed* as the key of *config* (a saved config)."""
    if config._state.adding:
        raise KeyChangeError(SAVE_FIRST)
    from_email = EmailServiceConfig.load().from_email
    try:
        subject = require_subject(config, from_email)
    except GmailScopeError:
        raise KeyChangeError(FROM_NOT_LISTED.format(address=from_email)) from None
    test = check_key(parsed, subject)
    _refuse_failed_test(config, parsed, test)
    stored = _store(parsed)
    _pin(config, parsed, stored, test, actor)
    return test


def _strict_reason(config, parsed: ParsedKey) -> str:
    """Why this install needs an issued token, or "" when a pending delegation is acceptable."""
    if config.key_configured and parsed.client_email == config.service_account_email:
        return "This replaces the key of the same service account"
    email = EmailServiceConfig.load()
    if config.is_active and email.is_active and email.provider == EmailServiceConfig.Provider.GMAIL:
        return "Email is sent through the Gmail API with this configuration"
    if config.is_active:
        return "This configuration is active"
    return ""


def _refuse_failed_test(config, parsed: ParsedKey, test: TokenTest) -> None:
    if test.outcome == ISSUED:
        return
    reason = _strict_reason(config, parsed)
    if reason:
        raise KeyChangeError(NEEDS_TOKEN.format(reason=reason, result=test.detail))
    if test.outcome != PENDING:
        raise KeyChangeError(NOT_ACCEPTED.format(result=test.detail))


@sensitive_variables()
def _store(parsed: ParsedKey):
    try:
        return stored_key.store_key(parsed.payload, parsed.private_key)
    except CredentialStoreError as exc:
        error = KeyChangeError(STORE_FAILED.format(error=exc))
    raise error


def _pin(config, parsed: ParsedKey, stored, test: TokenTest, actor) -> None:
    now = timezone.now()
    with transaction.atomic():
        locked = GmailApiProviderConfig.objects.select_for_update().get(pk=config.pk)
        if (locked.is_active, locked.service_account_email) != (config.is_active, config.service_account_email):
            raise KeyChangeError(CHANGED_MEANWHILE)
        GmailApiProviderConfig.objects.filter(pk=locked.pk).update(
            key_secret_ref=stored.arn,
            key_version_id=stored.version_id,
            service_account_email=parsed.client_email,
            client_id=parsed.client_id,
            key_id=parsed.key_id,
            project_id=parsed.project_id,
            key_installed_at=now,
            access_checked_at=None,
            updated_at=now,
        )
        GmailApiSubject.objects.filter(config=locked).update(verified_at=None, updated_at=now)
        message = f"Gmail API key installed: key id {parsed.key_id}, service account {parsed.client_email}."
        record(actor, locked, f"{message} {test.describe()}", action="installed", key_id=parsed.key_id)
        transaction.on_commit(partial(_relabel, stored.version_id))
        # The pin is written with update(), which sends no post_save: half-open a refused-credentials breaker here,
        # as a config save would, so the next send tries the new key at once.
        transaction.on_commit(partial(receivers.half_open_after_commit, (DeliveryChannel.GMAIL_API_SEND,)), robust=True)
    config.refresh_from_db()


def record(actor, config, message: str, *, action: str, key_id: str) -> None:
    """Admin history (LogEntry) plus one log line; both carry only public identifiers."""
    logger.info(
        "gmail_api_key_event action=%s key_id=%s config=%s actor=%s",
        action,
        key_id or "-",
        config.pk,
        getattr(actor, "pk", None) or "-",
    )
    if getattr(actor, "pk", None):
        LogEntry.objects.log_actions(
            user_id=actor.pk, queryset=[config], action_flag=CHANGE, change_message=message, single_object=True
        )


def _relabel(version_id: str) -> None:
    try:
        get_store().move_current(stored_key.KEY_NAME, version_id)
    except CredentialStoreError as exc:
        logger.warning("Gmail API key version could not be labelled current: %s", exc.code or "refused")
