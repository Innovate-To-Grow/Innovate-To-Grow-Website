"""The Graph requests of the access check, made with one access token. Each becomes a ``ProbeResult``.

The probes use the same requests as the site (the transport allowlist refuses anything else) but deliberately skip
the site's own scope check, because they test what Microsoft allows. No response body, message content or token
is kept: only the status, the allow-listed Graph error code and Microsoft's request id.

The probes Microsoft should allow share the scoped mailboxes' allowance with the site's own mail, so each is admitted
on its delivery channel (``graph_send`` or ``graph_read``) and its answer recorded. The probes that must be refused
target the deny mailbox and record nothing.
"""

import base64
import dataclasses
from urllib.parse import quote

from django.conf import settings
from django.views.decorators.debug import sensitive_variables

from apps.core.models.base.delivery_rates import DeliveryChannel
from apps.core.services.delivery_rates import RateDeferred, admit, mailbox_identity, record, release, uncertain
from apps.core.services.delivery_rates.adapters.graph import graph_signal

from ...contracts import EmailMessage
from ...exceptions import PermanentEmailDeliveryError
from ...mime import build_mime_message
from ...telemetry.probes import tracked_probe
from .. import json_message, transport
from ..errors import innermost_error_code
from .judge import judge, newest_id
from .report import (
    ALLOWED,
    DENIED,
    EXTRA_READ,
    FAIL,
    FOLDER,
    MESSAGES,
    NOT_IN_SCOPE,
    PASS,
    SEND,
    VALUE,
    WARN,
    ProbeResult,
    join_notes,
)

PROBE_SUBJECT = "I2G Microsoft Graph access check"
PROBE_BODY = (
    "Automated access check from the Innovate to Grow website. No action is needed; this message can be deleted."
)
NEWEST_MESSAGE = "$top=1&$select=id,bodyPreview&$orderby=receivedDateTime%20desc"
UNREACHABLE = "Graph could not be reached."
OUTCOME_UNKNOWN = "Graph outcome unknown: a probe email may have been sent."
EXTRA_READ_ALLOWED = (
    "Microsoft also allows reading this send-only mailbox: only the site's scope stops it (expected under an "
    "access policy, which limits mailboxes, not permissions)"
)
EXTRA_READ_REFUSED = "Microsoft refuses reading this send-only mailbox too"
RATE_HELD = "not run: Microsoft Graph is paced or cooling down for this mailbox; run the check again in about {} s"


def user_path(mailbox: str) -> str:
    return f"/v1.0/users/{quote(mailbox, safe='@')}"


class Prober:
    """Runs probes with one access token, which is never logged, stored or put in a result."""

    @sensitive_variables()
    def __init__(self, token: str, *, timeout: float):
        self._headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        self._timeout = timeout

    def folder(self, mailbox: str, *, expect_allowed: bool) -> ProbeResult:
        """The Inbox folder itself: read access to the mailbox."""
        return self._get(FOLDER, mailbox, f"{user_path(mailbox)}/mailFolders/inbox?$select=id", expect_allowed)

    def messages(self, mailbox: str, *, expect_allowed: bool) -> tuple[ProbeResult, str]:
        """The newest Inbox message (``bodyPreview`` needs Mail.Read, not just Mail.ReadBasic) and its id, or ""."""
        path = f"{user_path(mailbox)}/mailFolders/inbox/messages?{NEWEST_MESSAGE}"
        result, response = self._get_response(
            MESSAGES, mailbox, path, expect_allowed, settings.GRAPH_MAX_RESPONSE_BYTES
        )
        return result, (newest_id(response) if result.passed and expect_allowed else "")

    def extra_read(self, mailbox: str) -> ProbeResult:
        """Reading a mailbox the site's scope lets send only: shown for the record, never part of the verdict."""
        result = self._get(EXTRA_READ, mailbox, f"{user_path(mailbox)}/mailFolders/inbox?$select=id", False)
        if result.status == 403:
            note = join_notes(EXTRA_READ_REFUSED, result.note)
            return dataclasses.replace(result, expected=NOT_IN_SCOPE, outcome=PASS, note=note)
        note = EXTRA_READ_ALLOWED if result.status == 200 else result.note
        return dataclasses.replace(result, expected=NOT_IN_SCOPE, outcome=WARN, note=note)

    def value(self, mailbox: str, message_id: str) -> ProbeResult:
        """The start of one message's raw MIME, as the admin inbox opens it; the bytes are discarded."""
        path = f"{user_path(mailbox)}/messages/{message_id}/$value"
        max_bytes = settings.GRAPH_ACCESS_CHECK_MIME_MAX_BYTES
        return self._get_response(VALUE, mailbox, path, True, max_bytes)[0]

    @tracked_probe("mime", PROBE_SUBJECT)
    def send_mime(self, mailbox: str) -> ProbeResult:
        """A MIME sendMail from *mailbox* to itself, as the site sends most mail (Exchange keeps a Sent Items copy)."""
        message = EmailMessage(subject=PROBE_SUBJECT, to=(mailbox,), text_body=PROBE_BODY)
        try:
            body = base64.b64encode(build_mime_message(message, from_email=mailbox).as_bytes())
        except PermanentEmailDeliveryError as exc:
            return ProbeResult(SEND, mailbox, ALLOWED, FAIL, note=str(exc))
        result = self._post(SEND, mailbox, user_path(mailbox), body, "text/plain", expect_allowed=True)
        if result.status == 202:
            return _with_note(result, f"probe email sent to {mailbox}; a copy stays in its Sent Items")
        return result

    @tracked_probe("json", PROBE_SUBJECT)
    def send_json(self, check: str, *, url_mailbox: str, from_mailbox: str, recipient: str) -> ProbeResult:
        """A JSON sendMail Microsoft must refuse, with ``saveToSentItems`` false so a wrong 202 files no copy."""
        message = EmailMessage(subject=PROBE_SUBJECT, to=(recipient,), text_body=PROBE_BODY, keep_sent_copy=False)
        try:
            body = json_message.send_mail_body(message, from_email=from_mailbox)
        except PermanentEmailDeliveryError as exc:
            return ProbeResult(check, url_mailbox, DENIED, FAIL, note=str(exc))
        result = self._post(check, url_mailbox, user_path(url_mailbox), body, json_message.CONTENT_TYPE)
        send_as = f"From {from_mailbox}" if url_mailbox != from_mailbox else ""
        if result.status != 202:
            return _with_note(result, join_notes(send_as, result.note))
        granted = f"{url_mailbox} may send as {from_mailbox}" if send_as else ""
        sent = f"a probe email was sent to {recipient} (no Sent Items copy)"
        return _with_note(result, join_notes(result.note, granted, sent))

    def _get(self, check, mailbox, path, expect_allowed) -> ProbeResult:
        return self._get_response(check, mailbox, path, expect_allowed, settings.GRAPH_MAX_RESPONSE_BYTES)[0]

    def _get_response(self, check, mailbox, path, expect_allowed, max_bytes):
        expected = ALLOWED if expect_allowed else DENIED
        admission = _admit(DeliveryChannel.GRAPH_READ, mailbox) if expect_allowed else None
        if isinstance(admission, RateDeferred):
            return ProbeResult(check, mailbox, expected, FAIL, note=RATE_HELD.format(admission.retry_after)), None
        try:
            response = transport.get(
                transport.GRAPH_HOST, path, self._headers, timeout=self._timeout, max_bytes=max_bytes
            )
        except (transport.ConnectFailed, transport.ResponseLost):
            _settle(admission, None)
            return ProbeResult(check, mailbox, expected, FAIL, note=UNREACHABLE), None
        except transport.RequestNotAllowed as exc:
            _settle(admission, None)
            return ProbeResult(check, mailbox, expected, FAIL, note=str(exc)), None
        _settle(admission, _answer(response, read=True))
        return judge(check, mailbox, response, allowed_status=200, expect_allowed=expect_allowed), response

    def _post(self, check, mailbox, path, body, content_type, *, expect_allowed=False) -> ProbeResult:
        expected = ALLOWED if expect_allowed else DENIED
        admission = _admit(DeliveryChannel.GRAPH_SEND, mailbox) if expect_allowed else None
        if isinstance(admission, RateDeferred):
            return ProbeResult(check, mailbox, expected, FAIL, note=RATE_HELD.format(admission.retry_after))
        headers = {**self._headers, "Content-Type": content_type}
        try:
            response = transport.post(transport.GRAPH_HOST, f"{path}/sendMail", body, headers, timeout=self._timeout)
        except transport.ConnectFailed:
            _settle(admission, None)
            return ProbeResult(check, mailbox, expected, FAIL, note=UNREACHABLE)
        except transport.ResponseLost:
            _settle(admission, uncertain("response_lost"))
            return ProbeResult(check, mailbox, expected, FAIL, note=OUTCOME_UNKNOWN)
        except transport.RequestNotAllowed as exc:
            _settle(admission, None)
            return ProbeResult(check, mailbox, expected, FAIL, note=str(exc))
        _settle(admission, _answer(response, read=False))
        return judge(check, mailbox, response, allowed_status=202, expect_allowed=expect_allowed)


def _with_note(result: ProbeResult, note: str) -> ProbeResult:
    return dataclasses.replace(result, note=note)


def _admit(channel: str, mailbox: str):
    """The probe's admission on ``channel`` for ``mailbox``, or the ``RateDeferred`` that holds it back."""
    try:
        return admit(channel, mailbox_identity(mailbox))
    except RateDeferred as exc:
        return exc


def _answer(response: transport.HttpResponse, *, read: bool):
    return graph_signal(response.status, response.headers, innermost_error_code(response.body), read=read)


def _settle(admission, signal) -> None:
    """Record Microsoft's answer (None: it was never reached, so the slot is given back)."""
    if admission is None:
        return
    if signal is None:
        release(admission)
    else:
        record(admission, signal)
