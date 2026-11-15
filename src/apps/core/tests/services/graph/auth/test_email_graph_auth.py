"""Graph access tokens: the client-credentials request, the in-memory cache and failure classification."""

import dataclasses
from urllib.parse import parse_qs

from django.conf import settings
from django.test import SimpleTestCase

from apps.core.services.email.graph import auth
from apps.core.tests.graph_helpers import make_test_credential, private_key_lines
from apps.core.tests.services.graph.provider.test_email_graph import (
    ACCESS_TOKEN,
    CLIENT_ID,
    TENANT_ID,
    GraphFixtureMixin,
)


class FakeClock:
    """Replaces the ``time`` module inside ``auth`` so cache expiry can be driven without sleeping."""

    def __init__(self, now=1000.0):
        self.now = now

    def monotonic(self):
        return self.now


class TokenTestCase(GraphFixtureMixin, SimpleTestCase):
    def setUp(self):
        super().setUp()
        # Two installed certificates with different stored keys (so different pinned versions).
        self.credential = make_test_credential()
        self.other_credential = make_test_credential(key_index=1)

    def get_token(self, timeout=None, credential=None, **overrides):
        credential = dataclasses.replace(credential or self.credential, **overrides)
        if timeout is None:
            return auth.get_access_token(credential)
        return auth.get_access_token(credential, timeout=timeout)


class GraphTokenRequestTests(TokenTestCase):
    def test_posts_the_client_credentials_grant_to_the_tenant_token_endpoint(self):
        self.assertEqual(self.get_token(), ACCESS_TOKEN)

        (request,) = self.fake.requests
        self.assertEqual(request.host, "login.microsoftonline.com")
        self.assertEqual(request.path, f"/{TENANT_ID}/oauth2/v2.0/token")
        self.assertEqual(request.headers["Content-Type"], "application/x-www-form-urlencoded")
        form = parse_qs(request.body.decode("ascii"), strict_parsing=True)
        self.assertEqual(len(form.pop("client_assertion")), 1)
        self.assertEqual(
            form,
            {
                "client_id": [CLIENT_ID],
                "client_assertion_type": [auth.CLIENT_ASSERTION_TYPE],
                "scope": ["https://graph.microsoft.com/.default"],
                "grant_type": ["client_credentials"],
            },
        )

    def test_the_assertion_travels_only_in_the_form_body_and_the_key_never_travels(self):
        self.get_token()

        request = self.fake.requests[0]
        self.assertNotIn("client_secret", parse_qs(request.body.decode("ascii")))
        self.assertNotIn("Authorization", request.headers)
        for line in private_key_lines():
            self.assertNotIn(line, request.path + request.body.decode("ascii") + "".join(request.headers.values()))

    def test_tenant_is_percent_encoded_so_it_cannot_add_path_segments(self):
        cases = [
            ("contoso.onmicrosoft.com", "contoso.onmicrosoft.com"),
            ("a/b", "a%2Fb"),
            ("../x", "..%2Fx"),
            ("t?x=1#f", "t%3Fx%3D1%23f"),
        ]
        for tenant, segment in cases:
            with self.subTest(tenant=tenant):
                self.script()

                self.get_token(tenant_id=tenant)

                self.assertEqual(self.fake.requests[0].path, f"/{segment}/oauth2/v2.0/token")

    def test_timeout_defaults_to_the_module_setting_and_can_be_overridden(self):
        self.get_token()
        self.assertEqual(self.fake.requests[0].timeout, settings.GRAPH_REQUEST_TIMEOUT_SECONDS)

        self.script()
        self.get_token(timeout=7)
        self.assertEqual(self.fake.requests[0].timeout, 7)
