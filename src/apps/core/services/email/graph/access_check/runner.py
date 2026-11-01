"""Run the access check for one Graph config: a fresh token, its roles, then the mailbox probes."""

from django.conf import settings
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables

from apps.core.models import EmailServiceConfig
from apps.core.models.base.service_credentials.microsoft_graph import is_deny_mailbox, normalize_mailbox
from apps.core.utils.security import is_guid

from ...exceptions import EmailDeliveryError
from .. import auth
from ..access import READ, SEND, credential_for
from . import roles
from .probes import Prober
from .report import (
    ALLOWED,
    DENIED,
    FAIL,
    FOLDER,
    ISSUED,
    PASS,
    SEND_AS,
    SKIP,
    TOKEN,
    VALUE,
    WARN,
    AccessCheckReport,
    ProbeResult,
    pair_denials,
)
from .report import SEND as SEND_CHECK

NOT_READY = "The Microsoft Graph config needs a usable current certificate and a mailbox scope before it is checked."
NO_DENY_MAILBOX = "Set the Access Check Deny Mailbox (the test mailbox OIT / InfoSec designated) first."
INVALID_DENY_MAILBOX = "The deny mailbox must be a plain email address."
DENY_MAILBOX_IN_USE = (
    "The deny mailbox is in the mailbox scope, or is the sender mailbox or the From address; choose a mailbox "
    "outside the scope."
)
NO_READER = "no mailbox in the scope has read permission"
NO_SENDER = "no mailbox in the scope with send permission is listed by email address"
SENDS_SKIPPED = "send probes were not run"
GUID_SENDER = "listed by object ID: sending is probed only for mailboxes listed by email address"
EMPTY_INBOX = "the Inbox is empty (or its list was unreadable), so opening a message ($value) was not exercised"
LIST_FAILED = "the message list failed"


def precondition_problem(config, deny_mailbox: str) -> str:
    """Why *config* cannot be checked against *deny_mailbox*, or ""."""
    if config._state.adding or not config.credential_configured or not config.mailbox_scopes.exists():
        return NOT_READY
    deny = normalize_mailbox(deny_mailbox)
    if not deny:
        return NO_DENY_MAILBOX
    if not is_deny_mailbox(deny):
        return INVALID_DENY_MAILBOX
    in_use = {normalize_mailbox(config.mailbox), normalize_mailbox(EmailServiceConfig.load().from_email)}
    if deny in in_use or config.mailbox_scopes.filter(mailbox=deny).exists():
        return DENY_MAILBOX_IN_USE
    return ""


@sensitive_variables()
def run_access_check(config, *, deny_mailbox: str, send: bool = True) -> AccessCheckReport:
    """Request a fresh token with the current certificate, read its roles, then probe the scope and *deny_mailbox*."""
    certificate = config.current_certificate
    credential = credential_for(config)
    approved = roles.approved_roles()
    reference = config.permission_exception_reference
    timeout = settings.GRAPH_ACCESS_CHECK_TIMEOUT_SECONDS
    # A cached token could predate a change OIT made: its roles must show the grant as it is now.
    auth.forget_access_token(credential)
    try:
        token = auth.get_access_token(credential, timeout=timeout)
    except EmailDeliveryError as exc:
        granted, results = None, [ProbeResult(TOKEN, "-", ISSUED, FAIL, note=str(exc))]
    else:
        granted = roles.token_roles(token)
        results = [
            ProbeResult(TOKEN, "-", ISSUED, PASS, status=200, note="requested with the current certificate"),
            roles.roles_result(granted, approved, reference),
            *_mailbox_probes(Prober(token, timeout=timeout), config, deny_mailbox, send),
        ]
    return AccessCheckReport(
        results=tuple(pair_denials(results)),
        granted_roles=granted,
        approved_roles=approved,
        exception_reference=reference,
        tenant_id=config.tenant_id,
        client_id=config.client_id,
        certificate_id=certificate.pk,
        certificate_sha1=certificate.sha1_thumbprint,
        key_version_id=certificate.store_version_id,
        deny_mailbox=deny_mailbox,
        checked_at=timezone.now(),
    )


def _mailbox_probes(prober: Prober, config, deny_mailbox: str, send: bool) -> list[ProbeResult]:
    scopes = list(config.mailbox_scopes.all())
    readers = [scope.mailbox for scope in scopes if scope.grants(READ)]
    senders = [scope.mailbox for scope in scopes if scope.grants(SEND)]
    results = [result for mailbox in readers for result in _read_probes(prober, mailbox)]
    if not readers:
        results.append(ProbeResult(FOLDER, "-", ALLOWED, SKIP, note=NO_READER))
    results.extend(_allowed_send(prober, mailbox, send) for mailbox in senders)
    if not senders:
        results.append(ProbeResult(SEND_CHECK, "-", ALLOWED, SKIP, note=NO_SENDER))
    results.extend(prober.extra_read(mailbox) for mailbox in senders if mailbox not in readers)
    results.append(prober.folder(deny_mailbox, expect_allowed=False))
    results.append(prober.messages(deny_mailbox, expect_allowed=False)[0])
    results.extend(_denied_sends(prober, deny_mailbox, _probe_recipient(config, senders), send))
    return results


def _probe_recipient(config, senders: list[str]) -> str:
    """Where the sends that must be refused are addressed: the I2G sender mailbox, else any scoped sender address."""
    addresses = [mailbox for mailbox in senders if not is_guid(mailbox)]
    sender = config.sender_mailbox(EmailServiceConfig.load().from_email)
    return sender if sender in addresses else next(iter(addresses), "")


def _read_probes(prober: Prober, mailbox: str) -> list[ProbeResult]:
    folder = prober.folder(mailbox, expect_allowed=True)
    listing, newest = prober.messages(mailbox, expect_allowed=True)
    if newest:
        value = prober.value(mailbox, newest)
    elif listing.passed:
        value = ProbeResult(VALUE, mailbox, ALLOWED, WARN, note=EMPTY_INBOX)
    else:
        value = ProbeResult(VALUE, mailbox, ALLOWED, SKIP, note=LIST_FAILED)
    return [folder, listing, value]


def _allowed_send(prober: Prober, mailbox: str, send: bool) -> ProbeResult:
    if not send:
        return ProbeResult(SEND_CHECK, mailbox, ALLOWED, SKIP, note=SENDS_SKIPPED)
    if is_guid(mailbox):
        return ProbeResult(SEND_CHECK, mailbox, ALLOWED, SKIP, note=GUID_SENDER)
    return prober.send_mime(mailbox)


def _denied_sends(prober: Prober, deny_mailbox: str, recipient: str, send: bool) -> list[ProbeResult]:
    """Sending as the deny mailbox, then sending from the deny address through a scoped mailbox (Send As)."""
    if not send or not recipient:
        note = SENDS_SKIPPED if not send else NO_SENDER
        return [
            ProbeResult(SEND_CHECK, deny_mailbox, DENIED, SKIP, note=note),
            ProbeResult(SEND_AS, recipient or "-", DENIED, SKIP, note=note),
        ]
    return [
        prober.send_json(SEND_CHECK, url_mailbox=deny_mailbox, from_mailbox=deny_mailbox, recipient=recipient),
        prober.send_json(SEND_AS, url_mailbox=recipient, from_mailbox=deny_mailbox, recipient=recipient),
    ]
