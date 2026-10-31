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

from django.test import SimpleTestCase

from apps.core.services.email import EmailAttachment, EmailMessage, GraphProvider, PermanentEmailDeliveryError
from apps.core.services.email.graph import auth
from apps.core.services.email.graph import provider as graph_provider
from apps.core.services.email.graph.transport import HttpResponse
from apps.core.services.email.mime import build_mime_message
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


class GraphProviderConfigurationTests(SimpleTestCase):
    def test_provider_is_named_graph(self):
        self.assertEqual(make_provider().name, "graph")

    def test_accepts_domain_tenants_and_mailbox_object_ids(self):
        provider = make_provider(tenant_id="contoso.onmicrosoft.com", mailbox="72f988bf-86f1-41af-91ab-2d7cd011db47")

        self.assertEqual(provider.credential.tenant_id, "contoso.onmicrosoft.com")
        self.assertEqual(provider.mailbox, "72f988bf-86f1-41af-91ab-2d7cd011db47")

    def test_rejects_invalid_configuration_without_echoing_key_material(self):
        invalid = {
            "tenant without a dot": {"tenant_id": "common"},
            "tenant with a path separator": {"tenant_id": "a/b"},
            "blank tenant": {"tenant_id": ""},
            "client id that is not a guid": {"client_id": "not-a-guid"},
            "blank client id": {"client_id": ""},
            "mailbox that is not an address": {"mailbox": "not a mailbox"},
            "mailbox with an injected header": {"mailbox": "user@contoso.com\nBcc: evil@example.com"},
            "blank mailbox": {"mailbox": ""},
            "blank certificate thumbprint": {"x5t_s256": ""},
            "blank key reference": {"key_arn": ""},
            "blank key version": {"key_version_id": ""},
        }
        for label, overrides in invalid.items():
            with self.subTest(label):
                with self.assertRaisesMessage(PermanentEmailDeliveryError, "configuration is invalid") as caught:
                    make_provider(**overrides)
                for line in private_key_lines():
                    self.assertNotIn(line, str(caught.exception))

    def test_repr_does_not_expose_key_material(self):
        text = repr(make_provider())

        self.assertNotIn("PRIVATE KEY", text)
        for line in private_key_lines():
            self.assertNotIn(line, text)


class GraphProviderSendTests(GraphFixtureMixin, SimpleTestCase):
    def send(self, message=None, **provider_overrides):
        return make_provider(**provider_overrides).send(message or simple_message())

    def test_submits_the_message_to_send_mail_with_a_bearer_token(self):
        result = self.send()

        self.assertEqual(result.provider, "graph")
        self.assertTrue(result.accepted)
        self.assertEqual(
            [request.host for request in self.fake.requests], ["login.microsoftonline.com", "graph.microsoft.com"]
        )
        request = self.fake.send_requests[0]
        self.assertEqual(request.path, "/v1.0/users/sender@contoso.com/sendMail")
        self.assertEqual(request.headers["Authorization"], f"Bearer {ACCESS_TOKEN}")
        self.assertEqual(request.headers["Content-Type"], "text/plain")
        self.assertEqual(request.headers["Accept"], "application/json")

    def test_request_body_is_one_line_of_base64_mime(self):
        self.send(simple_message(subject="Greetings"))

        request = self.fake.send_requests[0]
        self.assertNotIn(b"\n", request.body)
        self.assertEqual(sent_mime(request)["Subject"], "Greetings")

    def test_result_message_id_is_the_mime_message_id(self):
        result = self.send()

        mime_message_id = str(sent_mime(self.fake.send_requests[0])["Message-ID"])
        self.assertEqual(result.message_id, mime_message_id)
        self.assertTrue(result.message_id.startswith("<") and result.message_id.endswith(">"))

    def test_every_send_gets_its_own_message_id(self):
        provider = make_provider()

        first = provider.send(simple_message())
        second = provider.send(simple_message())

        self.assertNotEqual(first.message_id, second.message_id)

    def test_mailbox_is_percent_encoded_into_the_path_but_keeps_the_at_sign(self):
        cases = [
            ("sender@contoso.com", "sender@contoso.com"),
            ("user+tag@contoso.com", "user%2Btag@contoso.com"),
            ("o'brien@contoso.com", "o%27brien@contoso.com"),
            # Valid for the address validator, yet it must not be able to add path segments or a query string.
            ("a/b?c#d@contoso.com", "a%2Fb%3Fc%23d@contoso.com"),
            ("72f988bf-86f1-41af-91ab-2d7cd011db47", "72f988bf-86f1-41af-91ab-2d7cd011db47"),
        ]
        for mailbox, segment in cases:
            with self.subTest(mailbox=mailbox):
                self.script()

                self.send(mailbox=mailbox)

                self.assertEqual(self.fake.send_requests[0].path, f"/v1.0/users/{segment}/sendMail")

    def test_addressing_and_threading_headers_survive_the_mime_round_trip(self):
        self.send(ticket_message())

        mime = sent_mime(self.fake.send_requests[0])
        self.assertEqual(mime["Subject"], TICKET_SUBJECT)
        self.assertEqual(mime["From"], "Innovate to Grow <sender@contoso.com>")
        self.assertEqual(mime["To"], "to1@example.com, to2@example.com")
        self.assertEqual(mime["Cc"], "cc@example.com")
        self.assertEqual(mime["Reply-To"], "replies@example.com")
        # A long header is folded after its name on the wire, so unfold it before comparing.
        unsubscribe = " ".join(str(mime["List-Unsubscribe"]).split())
        self.assertEqual(unsubscribe, "<mailto:unsubscribe@example.com>, <https://example.com/unsubscribe/abc>")
        self.assertEqual(mime["List-Unsubscribe-Post"], "List-Unsubscribe=One-Click")
        self.assertEqual(mime["In-Reply-To"], "<original@example.com>")
        self.assertEqual(mime["References"], "<root@example.com> <original@example.com>")
        self.assertIsNone(mime["Bcc"])

    def test_from_header_is_the_bare_address_without_a_display_name(self):
        self.send(from_name="")

        self.assertEqual(sent_mime(self.fake.send_requests[0])["From"], "sender@contoso.com")

    def test_from_header_uses_the_from_address_rather_than_the_sending_mailbox(self):
        self.send(mailbox="shared@contoso.com", from_email="noreply@example.com", from_name="")

        request = self.fake.send_requests[0]
        self.assertEqual(request.path, "/v1.0/users/shared@contoso.com/sendMail")
        self.assertEqual(sent_mime(request)["From"], "noreply@example.com")

    def test_html_inline_image_and_attachment_survive_the_mime_round_trip(self):
        self.send(ticket_message())

        mime = sent_mime(self.fake.send_requests[0])
        html = mime.get_body(preferencelist=("html",))
        self.assertIn('<img src="cid:qr-code">', html.get_content())
        parts = {part.get_filename(): part for part in mime.walk() if part.get_filename()}
        inline = parts["qr.png"]
        self.assertEqual(inline.get_content_disposition(), "inline")
        self.assertEqual(inline["Content-ID"], "<qr-code>")
        self.assertEqual(inline.get_content_type(), "image/png")
        self.assertEqual(inline.get_payload(decode=True), b"inline-image-bytes")
        attachment = parts["ticket.ics"]
        self.assertEqual(attachment.get_content_disposition(), "attachment")
        self.assertEqual(attachment.get_payload(decode=True), b"BEGIN:VCALENDAR")

    def test_text_and_html_bodies_are_sent_as_alternatives(self):
        self.send(ticket_message())

        mime = sent_mime(self.fake.send_requests[0])
        self.assertIn("multipart/alternative", [part.get_content_type() for part in mime.walk()])
        self.assertEqual(mime.get_body(preferencelist=("plain",)).get_content().strip(), "Plain body")
        self.assertIn("HTML body", mime.get_body(preferencelist=("html",)).get_content())

    def test_html_only_message_has_no_plain_part(self):
        self.send(simple_message(text_body=None, html_body="<p>Only HTML</p>"))

        mime = sent_mime(self.fake.send_requests[0])
        self.assertEqual(mime.get_content_type(), "text/html")
        self.assertIn("Only HTML", mime.get_content())

    def test_consecutive_sends_reuse_one_access_token(self):
        provider = make_provider()

        provider.send(simple_message())
        provider.send(simple_message())

        self.assertEqual(len(self.fake.token_requests), 1)
        self.assertEqual(len(self.fake.send_requests), 2)

    def test_timeout_reaches_both_the_token_and_the_send_request(self):
        self.send()
        self.assertEqual([request.timeout for request in self.fake.requests], [auth.REQUEST_TIMEOUT] * 2)

        self.script()
        self.send(timeout=7)
        self.assertEqual([request.timeout for request in self.fake.requests], [7, 7])

    def test_credentials_stay_out_of_the_send_request_url_and_body(self):
        self.send()

        request = self.fake.send_requests[0]
        self.assertNotIn(ACCESS_TOKEN, request.path)
        self.assertNotIn(ACCESS_TOKEN.encode(), request.body)
        for line in private_key_lines():
            for sent in (request.path, request.body.decode("ascii"), "".join(request.headers.values())):
                self.assertNotIn(line, sent)
        carrying_the_token = [name for name, value in request.headers.items() if ACCESS_TOKEN in value]
        self.assertEqual(carrying_the_token, ["Authorization"])


class MessageIdDomainTests(GraphFixtureMixin, SimpleTestCase):
    def test_graph_messages_use_the_sender_domain_in_their_message_id(self):
        result = make_provider(from_email="sender@contoso.com", mailbox="sender@contoso.com").send(simple_message())

        message_id = str(sent_mime(self.fake.send_requests[0])["Message-ID"])
        self.assertEqual(result.message_id, message_id)
        self.assertTrue(message_id.endswith("@contoso.com>"), message_id)

    def test_the_shared_builder_never_falls_back_to_the_host_name_for_a_valid_sender(self):
        mime = build_mime_message(simple_message(), from_email="i2g@g.ucmerced.edu", from_name="I2G")

        self.assertTrue(str(mime["Message-ID"]).endswith("@g.ucmerced.edu>"))

    def test_a_sender_without_a_domain_still_gets_a_message_id(self):
        self.assertTrue(build_mime_message(simple_message(), from_email="not-an-address")["Message-ID"])
