"""Prove the tenant-side restriction: the Entra app reaches the scoped mailboxes and is refused for another one.

These probes deliberately bypass the site's own scope check (``access.require_mailbox``): they test what Microsoft
allows, which is what InfoSec needs to see. Every probe email is addressed to a scoped mailbox, so even a send that
Exchange wrongly allows can only land in the I2G mailbox itself.
"""

import base64
from dataclasses import dataclass
from urllib.parse import quote

from ..contracts import EmailMessage
from ..exceptions import EmailDeliveryError
from ..mime import build_mime_message
from . import auth, transport
from .access import READ, SEND, credential_for
from .errors import graph_error_code
from .provider import GRAPH_HOST

PROBE_SUBJECT = "I2G Microsoft Graph access check"
PROBE_BODY = (
    "Automated access check from the Innovate to Grow website (manage.py verify_graph_access). "
    "No action is needed; this message can be deleted."
)


@dataclass(frozen=True)
class ProbeResult:
    check: str
    mailbox: str
    expected: str
    status: int | None
    code: str
    passed: bool
    note: str = ""


def run_access_check(config, *, deny_mailbox: str, send: bool = True, timeout: float = 30) -> list[ProbeResult]:
    """Token, then each scoped mailbox (expect allowed), then *deny_mailbox* (expect refused)."""
    credential = credential_for(config)
    try:
        token = auth.get_access_token(credential, timeout=timeout)
    except EmailDeliveryError as exc:
        return [ProbeResult("token", "-", "issued", None, "", False, str(exc))]
    results = [ProbeResult("token", "-", "issued", 200, "", True)]
    scopes = list(config.mailbox_scopes.all())
    for scope in scopes:
        if scope.grants(READ):
            results.append(_probe_read(token, scope.mailbox, expect_allowed=True, timeout=timeout))
        if send and scope.grants(SEND):
            results.append(_probe_send(token, scope.mailbox, scope.mailbox, expect_allowed=True, timeout=timeout))
    results.append(_probe_read(token, deny_mailbox, expect_allowed=False, timeout=timeout))
    recipient = next((scope.mailbox for scope in scopes if scope.grants(SEND)), "")
    if send and recipient:
        results.append(_probe_send(token, deny_mailbox, recipient, expect_allowed=False, timeout=timeout))
    return results


def _probe_read(token: str, mailbox: str, *, expect_allowed: bool, timeout: float) -> ProbeResult:
    path = f"/v1.0/users/{quote(mailbox, safe='@')}/mailFolders/inbox?$select=id"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    try:
        response = transport.get(GRAPH_HOST, path, headers, timeout=timeout, max_bytes=transport.MAX_RESPONSE_BYTES)
    except (transport.ConnectFailed, transport.ResponseLost):
        return ProbeResult("read", mailbox, _expected(expect_allowed), None, "", False, "Graph could not be reached.")
    except transport.RequestNotAllowed as exc:
        return ProbeResult("read", mailbox, _expected(expect_allowed), None, "", False, str(exc))
    return _judge("read", mailbox, response, allowed_status=200, expect_allowed=expect_allowed)


def _probe_send(token: str, sender: str, recipient: str, *, expect_allowed: bool, timeout: float) -> ProbeResult:
    message = EmailMessage(subject=PROBE_SUBJECT, to=(recipient,), text_body=PROBE_BODY)
    payload = base64.b64encode(build_mime_message(message, from_email=sender).as_bytes())
    path = f"/v1.0/users/{quote(sender, safe='@')}/sendMail"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "text/plain", "Accept": "application/json"}
    try:
        response = transport.post(GRAPH_HOST, path, payload, headers, timeout=timeout)
    except (transport.ConnectFailed, transport.ResponseLost):
        return ProbeResult("send", sender, _expected(expect_allowed), None, "", False, "Graph outcome unknown.")
    except transport.RequestNotAllowed as exc:
        return ProbeResult("send", sender, _expected(expect_allowed), None, "", False, str(exc))
    result = _judge("send", sender, response, allowed_status=202, expect_allowed=expect_allowed)
    if response.status == 202:
        return ProbeResult(**{**result.__dict__, "note": f"probe email sent to {recipient}"})
    return result


def _judge(check, mailbox, response, *, allowed_status, expect_allowed) -> ProbeResult:
    code = graph_error_code(response.body)
    if expect_allowed:
        passed, note = response.status == allowed_status, ""
    else:
        passed = response.status == 403
        note = "mailbox not found: use an existing mailbox outside the scope" if response.status == 404 else ""
        if response.status == allowed_status:
            note = "ACCESS WAS GRANTED: the tenant-side restriction is missing"
    return ProbeResult(check, mailbox, _expected(expect_allowed), response.status, code, passed, note)


def _expected(expect_allowed: bool) -> str:
    return "allowed" if expect_allowed else "denied (403)"
