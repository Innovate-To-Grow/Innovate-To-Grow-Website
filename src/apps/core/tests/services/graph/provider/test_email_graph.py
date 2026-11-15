"""Microsoft Graph email provider: configuration checks, request shape and MIME content.

The other ``test_email_graph_*`` modules cover the callback boundary and failure classification (``_boundary``),
access tokens (``_auth``), the HTTPS client (``_transport``), response parsing (``_errors``) and the
registry/facade (``_registry``). They reuse the fakes defined at the top of this module, which replace
``transport.post`` so no test ever opens a socket.
"""

import base64
import dataclasses
import email
import email.policy
import json
from typing import NamedTuple
from unittest.mock import patch

from apps.core.services.email import EmailAttachment, EmailMessage, GraphProvider
from apps.core.services.email.graph import auth
from apps.core.services.email.graph import provider as graph_provider
from apps.core.services.email.graph.transport import HttpResponse
from apps.core.tests.graph_helpers import CLIENT_ID as CLIENT_ID  # re-exported for the other Graph test modules
from apps.core.tests.graph_helpers import TENANT_ID as TENANT_ID
from apps.core.tests.graph_helpers import make_test_credential, private_key_lines

ACCESS_TOKEN = "not-a-real-access-token"
# A line of the shared test certificate's private key: like the token, it must never reach a message or a log.
KEY_LINE = private_key_lines()[1]
MAILBOX = "sender@contoso.com"
REQUEST_ID = "8a1b2c3d-1111-2222-3333-444455556666"
# Stands in for the free text of a Microsoft error body; it must never reach an exception message or a log line.
RESPONSE_TEXT = "body-text-that-must-never-be-surfaced"
# Non-ASCII on purpose: the subject must survive MIME encoding (RFC 2047) and decoding unchanged.
TICKET_SUBJECT = "Your ticket \N{EN DASH} caf\N{LATIN SMALL LETTER E WITH ACUTE}"
POST_TARGET = "apps.core.services.email.graph.transport.post"
PROVIDER_LOGGER = "apps.core.services.email.graph.provider"


def token_response(token=ACCESS_TOKEN, expires_in=3599):
    """A successful identity-platform answer; ``expires_in=None`` leaves the field out."""
    payload = {"token_type": "Bearer", "access_token": token}
    if expires_in is not None:
        payload["expires_in"] = expires_in
    return HttpResponse(200, {}, json.dumps(payload).encode())


def graph_response(status=202, *, body=b"", headers=None):
    """A sendMail answer; header names are lower-cased because that is what the transport returns."""
    return HttpResponse(status, headers or {}, body)


def error_body(code):
    """A Graph error body that carries both an allow-listed code and free text."""
    return json.dumps(
        {"error": {"code": code, "message": RESPONSE_TEXT, "innerError": {"date": "2026-10-26"}}}
    ).encode()


class Request(NamedTuple):
    host: str
    path: str
    body: bytes
    headers: dict
    timeout: float


class FakeGraph:
    """Stands in for ``transport.post``: answers the identity platform and Graph, recording requests in order.

    An outcome is an ``HttpResponse``, an exception instance (raised) or a list of those. A list is consumed one
    entry per request with the last entry repeating, so a test can script "401 first, then 202".
    """

    def __init__(self):
        self.log = None
        self.requests = []
        self.outcomes = {}
        self.script()

    def script(self, *, token=None, send=None):
        self.requests.clear()
        self.outcomes = {
            auth.AUTHORITY_HOST: token or token_response(),
            graph_provider.GRAPH_HOST: send or graph_response(),
        }

    def __call__(self, host, path, body, headers, *, timeout):
        self.requests.append(Request(host, path, body, headers, timeout))
        if self.log is not None:
            self.log.append("token" if host == auth.AUTHORITY_HOST else "sendMail")
        outcome = self.outcomes[host]
        if isinstance(outcome, list):
            outcome = outcome.pop(0) if len(outcome) > 1 else outcome[0]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    @property
    def token_requests(self):
        return [request for request in self.requests if request.host == auth.AUTHORITY_HOST]

    @property
    def send_requests(self):
        return [request for request in self.requests if request.host == graph_provider.GRAPH_HOST]


class GraphFixtureMixin:
    """Per test: an empty token cache and ``transport.post`` replaced by ``self.fake``."""

    def setUp(self):
        super().setUp()
        auth.clear_access_token_cache()
        self.addCleanup(auth.clear_access_token_cache)
        self.fake = FakeGraph()
        patcher = patch(POST_TARGET, new=self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)

    def script(self, *, token=None, send=None):
        """Start over with an empty token cache and new scripted answers (for loops of subTests)."""
        auth.clear_access_token_cache()
        self.fake.script(token=token, send=send)


CREDENTIAL_FIELDS = tuple(field.name for field in dataclasses.fields(auth.GraphCredential))


def make_provider(**overrides):
    """A provider whose certificate key is in the credential store; credential fields can be overridden by name."""
    credential = overrides.pop("credential", None) or make_test_credential()
    changes = {name: overrides.pop(name) for name in CREDENTIAL_FIELDS if name in overrides}
    values = {
        "credential": dataclasses.replace(credential, **changes),
        "mailbox": MAILBOX,
        "from_email": MAILBOX,
        "from_name": "Innovate to Grow",
    }
    return GraphProvider(**{**values, **overrides})


def simple_message(**overrides):
    values = {"subject": "Subject", "to": ("to@example.com",), "text_body": "Body"}
    return EmailMessage(**{**values, **overrides})


def ticket_message():
    """A message using everything the callers need: threading and unsubscribe headers, inline image, attachment."""
    return EmailMessage(
        subject=TICKET_SUBJECT,
        to=("to1@example.com", "to2@example.com"),
        cc=("cc@example.com",),
        reply_to=("replies@example.com",),
        text_body="Plain body",
        html_body='<p>HTML body <img src="cid:qr-code"></p>',
        attachments=(
            EmailAttachment("qr.png", b"inline-image-bytes", "image/png", disposition="inline", content_id="qr-code"),
            EmailAttachment("ticket.ics", b"BEGIN:VCALENDAR", "text/calendar"),
        ),
        headers={
            "List-Unsubscribe": "<mailto:unsubscribe@example.com>, <https://example.com/unsubscribe/abc>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            "In-Reply-To": "<original@example.com>",
            "References": "<root@example.com> <original@example.com>",
        },
    )


def sent_mime(request):
    """The MIME message carried, base64-encoded, in a sendMail request body."""
    return email.message_from_bytes(base64.b64decode(request.body, validate=True), policy=email.policy.default)
