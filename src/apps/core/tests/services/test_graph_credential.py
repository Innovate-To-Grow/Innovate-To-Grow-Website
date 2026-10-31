"""``GraphCredential`` and the signing path: on each token request the private key is read from the credential store
by its pinned version, checked against the certificate, used once and dropped."""

import dataclasses
import uuid
from unittest.mock import patch
from urllib.parse import parse_qs

import jwt
from django.core.cache import caches
from django.test import SimpleTestCase, override_settings

from apps.core.services.credential_store import CredentialStoreError, TransientCredentialStoreError
from apps.core.services.email import PermanentEmailDeliveryError, TransientEmailDeliveryError
from apps.core.services.email.graph import auth
from apps.core.services.email.graph.certificate import describe_certificate
from apps.core.services.email.graph.credential import stored_key
from apps.core.tests.graph_helpers import make_certificate, make_test_credential, private_key_lines
from apps.core.tests.services.test_email_graph import (
    ACCESS_TOKEN,
    CLIENT_ID,
    TENANT_ID,
    GraphFixtureMixin,
    make_provider,
    simple_message,
)

AUDIENCE = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
READ_KEY = "apps.core.services.email.graph.credential.stored_key.read_key"
LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "graph-credential"}}


def form(request):
    return {name: values[0] for name, values in parse_qs(request.body.decode()).items()}


def credential_for_certificate(certificate, key):
    facts = describe_certificate(certificate)
    stored = stored_key.store_key(key)
    return auth.GraphCredential(
        tenant_id=TENANT_ID,
        client_id=CLIENT_ID,
        x5t_s256=facts.x5t_s256,
        public_key_sha256=facts.public_key_sha256,
        key_arn=stored.arn,
        key_version_id=stored.version_id,
    )


class GraphCredentialTests(SimpleTestCase):
    def test_holds_only_identifiers_and_pointers(self):
        names = {field.name for field in dataclasses.fields(auth.GraphCredential)}

        self.assertEqual(
            names, {"tenant_id", "client_id", "x5t_s256", "public_key_sha256", "key_arn", "key_version_id"}
        )
        text = repr(make_test_credential())
        self.assertNotIn("PRIVATE", text)
        for line in private_key_lines():
            self.assertNotIn(line, text)

    def test_cache_key_is_the_app_plus_the_pinned_version_and_thumbprint(self):
        credential = make_test_credential()

        self.assertEqual(credential.cache_key(), (TENANT_ID, CLIENT_ID, credential.key_version_id, credential.x5t_s256))


class CertificateTokenRequestTests(GraphFixtureMixin, SimpleTestCase):
    def setUp(self):
        super().setUp()
        self.certificate, self.key = make_certificate()
        self.credential = credential_for_certificate(self.certificate, self.key)

    def test_token_request_carries_an_assertion_signed_by_the_certificate_key(self):
        token = auth.get_access_token(self.credential)

        self.assertEqual(token, ACCESS_TOKEN)
        (request,) = self.fake.token_requests
        fields = form(request)
        self.assertNotIn("client_secret", fields)
        self.assertEqual(fields["client_assertion_type"], auth.CLIENT_ASSERTION_TYPE)
        claims = jwt.decode(
            fields["client_assertion"], self.certificate.public_key(), algorithms=["PS256"], audience=AUDIENCE
        )
        self.assertEqual(claims["sub"], CLIENT_ID)
        self.assertEqual(jwt.get_unverified_header(fields["client_assertion"])["x5t#S256"], self.credential.x5t_s256)
        self.assertNotIn(b"PRIVATE", request.body)

    def test_the_pinned_version_is_read_on_every_token_request_and_never_kept(self):
        with patch(READ_KEY, wraps=stored_key.read_key) as read_key:
            auth.get_access_token(self.credential)
            auth.get_access_token(self.credential)  # served from the token cache: no key read
            auth.clear_access_token_cache()
            auth.get_access_token(self.credential)

        self.assertEqual(read_key.call_count, 2)
        read_key.assert_called_with(
            arn=self.credential.key_arn,
            version_id=self.credential.key_version_id,
            expected_public_key_sha256=self.credential.public_key_sha256,
        )
        self.assertEqual(len(self.fake.token_requests), 2)

    def test_store_failures_are_classified_before_any_request(self):
        cases = [
            (TransientCredentialStoreError("throttled", code="ThrottlingException"), TransientEmailDeliveryError),
            (CredentialStoreError("denied", code="AccessDeniedException"), PermanentEmailDeliveryError),
        ]
        for failure, expected in cases:
            with self.subTest(expected.__name__):
                self.script()
                with patch(READ_KEY, side_effect=failure):
                    with self.assertRaises(expected) as caught:
                        auth.get_access_token(self.credential)

                self.assertIn(failure.code, str(caught.exception))
                self.assertIsNone(caught.exception.__context__)
                self.assertEqual(self.fake.requests, [])

    def test_a_pinned_key_that_does_not_match_the_certificate_fails_closed(self):
        other = make_test_credential(key_index=1)
        cases = {
            "another certificate's key hash": {"public_key_sha256": other.public_key_sha256},
            "another certificate's version": {"key_version_id": other.key_version_id},
        }
        for label, changes in cases.items():
            with self.subTest(label):
                with self.assertRaisesMessage(PermanentEmailDeliveryError, "does not match the installed certificate"):
                    auth.get_access_token(dataclasses.replace(self.credential, **changes))
        self.assertEqual(self.fake.requests, [])

    def test_unknown_versions_and_foreign_references_fail_closed(self):
        cases = {
            "unknown version": {"key_version_id": str(uuid.uuid4())},
            "another store's reference": {"key_arn": "arn:aws:secretsmanager:us-west-2:1:secret:x-AbCdEf"},
        }
        for label, changes in cases.items():
            with self.subTest(label):
                with self.assertRaisesMessage(PermanentEmailDeliveryError, "private key could not be read"):
                    auth.get_access_token(dataclasses.replace(self.credential, **changes))
        self.assertEqual(self.fake.requests, [])

    def test_provider_with_a_certificate_sends_through_the_assertion(self):
        provider = make_provider(credential=self.credential)

        provider.send(simple_message())

        token_request, send_request = self.fake.requests
        self.assertIn("client_assertion", form(token_request))
        self.assertEqual(send_request.headers["Authorization"], f"Bearer {ACCESS_TOKEN}")

    @override_settings(CACHES=LOCMEM)
    def test_tokens_and_keys_never_reach_the_shared_cache(self):
        caches["default"].clear()

        make_provider(credential=self.credential).send(simple_message())

        stored = b"".join(caches["default"]._cache.values())
        self.assertNotIn(ACCESS_TOKEN.encode(), stored)
        for line in private_key_lines(self.key):
            self.assertNotIn(line.encode(), stored)
