"""Fixtures for the Microsoft Graph access check: a fake Microsoft that answers per mailbox and request kind.

``ProbeFake`` replaces ``transport.post`` and ``transport.get`` (keeping their allowlist), so no socket opens. By
default it behaves like a
correct tenant restriction: the scoped mailbox is allowed everything, the deny mailbox is refused everything, and
a scoped mailbox may not send with another address as From (403 ``ErrorSendAsDenied``).
"""

import base64
import json
from unittest.mock import patch

from django.core.cache import cache

from apps.core.models import EmailServiceConfig, MicrosoftGraphAccessCheck
from apps.core.services.email.graph import auth, transport
from apps.core.services.email.graph.transport import HttpResponse
from apps.core.tests.graph_helpers import CLIENT_ID, TENANT_ID, create_graph_config
from apps.core.tests.services.test_email_graph import error_body, token_response

SCOPED = "i2g@contoso.com"
DENY = "intruder-test@contoso.com"
MESSAGE_ID = "AAMkAGI2THVSAAA="
REQUEST_ID = "8a1b2c3d-1111-2222-3333-444455556666"
APPROVED = ("Mail.Read", "Mail.Send")
# What OIT configured on the app: beyond the approval (Mail.Read), accepted as a broader grant that covers it.
OIT_ROLES = ("Mail.ReadWrite", "Mail.Send")
# A role beyond the approval that is not an accepted broader grant: it still needs an InfoSec exception reference.
UNACCEPTED_ROLES = ("Mail.Send", "User.Read.All")
APA_MESSAGE = "Access to OData is disabled: [RAOP] : Blocked by tenant configured AppOnly AccessPolicy settings."

ALLOW = {
    "folder": HttpResponse(200, {"request-id": REQUEST_ID}, b'{"id": "inbox"}'),
    "list": HttpResponse(200, {}, json.dumps({"value": [{"id": MESSAGE_ID, "bodyPreview": "hi"}]}).encode()),
    "value": HttpResponse(200, {}, b"Subject: hi\r\n\r\nbody", truncated=True),
    "send": HttpResponse(202, {}, b""),
}
DENIED = HttpResponse(403, {"request-id": REQUEST_ID}, error_body("ErrorAccessDenied"))
SEND_AS_DENIED = HttpResponse(403, {}, error_body("ErrorSendAsDenied"))
EMPTY_LIST = HttpResponse(200, {}, b'{"value": []}')


def jwt(payload) -> str:
    """An unsigned JWT-shaped access token whose payload is *payload* (the site never verifies it)."""

    def part(data):
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    return f"{part({'alg': 'RS256', 'typ': 'JWT'})}.{part(payload)}.c2lnbmF0dXJl"


def token_with_roles(roles=APPROVED) -> str:
    claims = {"aud": "https://graph.microsoft.com", "tid": TENANT_ID, "appid": CLIENT_ID}
    if roles is not None:
        claims["roles"] = list(roles)
    return jwt(claims)


def kind_of(method: str, path: str) -> str:
    if method == "POST":
        return "send"
    if path.endswith("/$value"):
        return "value"
    return "list" if "/messages" in path else "folder"


class ProbeFake:
    def __init__(self, roles=APPROVED):
        self.token = token_response(token=token_with_roles(roles))
        self.answers = {}
        self.calls = []

    def answer(self, mailbox, kind, response):
        self.answers[(mailbox, kind)] = response

    def _respond(self, method, path, body, headers):
        mailbox, kind = path.split("/")[3], kind_of(method, path)
        if (mailbox, kind) in self.answers:
            outcome = self.answers[(mailbox, kind)]
        elif mailbox == DENY:
            outcome = DENIED
        elif kind == "send" and headers.get("Content-Type") == "application/json" and _json_from(body) != mailbox:
            outcome = SEND_AS_DENIED
        else:
            outcome = ALLOW[kind]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def post(self, host, path, body, headers, *, timeout):
        # Like the real transport: a request off the allowlist is refused before anything is "sent".
        if not transport.is_allowed("POST", host, path):
            raise transport.RequestNotAllowed()
        self.calls.append(("POST", host, path, body, headers))
        if host == auth.AUTHORITY_HOST:
            if isinstance(self.token, Exception):
                raise self.token
            return self.token
        return self._respond("POST", path, body, headers)

    def get(self, host, path, headers, *, timeout, max_bytes):
        if not transport.is_allowed("GET", host, path):
            raise transport.RequestNotAllowed()
        self.calls.append(("GET", host, path, max_bytes, headers))
        return self._respond("GET", path, None, headers)

    def graph_calls(self):
        return [call for call in self.calls if call[1] != auth.AUTHORITY_HOST]


def _json_from(body: bytes) -> str:
    return json.loads(body)["message"]["from"]["emailAddress"]["address"]


def outcomes(report_or_results):
    results = getattr(report_or_results, "results", report_or_results)
    return [(result.outcome, result.check, result.mailbox) for result in results]


class ProbeFixtureMixin:
    """A Graph config scoped to ``SCOPED`` (send and read) with ``DENY`` as its designated deny mailbox."""

    def setUp(self):
        super().setUp()
        cache.clear()
        auth.clear_access_token_cache()
        self.addCleanup(auth.clear_access_token_cache)
        self.probe = ProbeFake()
        for name in ("post", "get"):
            patcher = patch.object(transport, name, new=getattr(self.probe, name))
            patcher.start()
            self.addCleanup(patcher.stop)
        self.config = create_graph_config(
            scope=(SCOPED,),
            name="Graph",
            is_active=True,
            mailbox=SCOPED,
            access_check_deny_mailbox=DENY,
        )
        EmailServiceConfig.objects.create(name="Mail", is_active=True, provider="ses", from_email=SCOPED)

    def use_roles(self, roles):
        self.probe.token = token_response(token=token_with_roles(roles))


Verdict = MicrosoftGraphAccessCheck.Verdict
