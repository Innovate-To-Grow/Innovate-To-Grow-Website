import json
from unittest.mock import patch

from apps.core.services.email.graph.identity import auth
from apps.core.services.email.graph.transport import HttpResponse
from apps.core.tests.graph_helpers import private_key_lines
from apps.core.tests.services.graph.auth.test_email_graph_auth import FakeClock, TokenTestCase
from apps.core.tests.services.graph.provider.test_email_graph import (
    ACCESS_TOKEN,
    CLIENT_ID,
    TENANT_ID,
    token_response,
)


class GraphTokenCacheTests(TokenTestCase):
    def test_a_second_call_is_served_from_the_cache(self):
        self.script(token=[token_response("token-one"), token_response("token-two")])

        self.assertEqual(self.get_token(), "token-one")
        self.assertEqual(self.get_token(), "token-one")

        self.assertEqual(len(self.fake.token_requests), 1)

    def test_an_expired_token_is_requested_again_and_the_replacement_is_cached(self):
        self.script(token=[token_response("token-one"), token_response("token-two")])
        clock = FakeClock(1000.0)

        with patch.object(auth, "time", clock):
            self.assertEqual(self.get_token(), "token-one")
            clock.now = 1000.0 + 3298  # one second before 3599 - 300 seconds
            self.assertEqual(self.get_token(), "token-one")
            clock.now = 1000.0 + 3299  # expired exactly at the margin-adjusted lifetime
            self.assertEqual(self.get_token(), "token-two")
            clock.now = 1000.0 + 3299 + 3298  # the replacement has a fresh lifetime of its own
            self.assertEqual(self.get_token(), "token-two")

        self.assertEqual(len(self.fake.token_requests), 2)

    def test_lifetimes_are_cached_for_the_documented_share_of_their_length(self):
        cases = [
            # expires_in, seconds the token stays cached
            (3599, 3299),  # longer than 10 minutes: the lifetime minus a 5 minute safety margin
            (3600, 3300),
            (601, 301),
            (600, 300),  # 10 minutes or less: half the lifetime
            (100, 50),
            (2, 1),
        ]
        for expires_in, cached_for in cases:
            with self.subTest(expires_in=expires_in):
                self.script(token=[token_response("token-one", expires_in), token_response("token-two", expires_in)])
                clock = FakeClock(1000.0)

                with patch.object(auth, "time", clock):
                    self.assertEqual(self.get_token(), "token-one")
                    clock.now = 1000.0 + cached_for - 1
                    self.assertEqual(self.get_token(), "token-one")
                    clock.now = 1000.0 + cached_for
                    self.assertEqual(self.get_token(), "token-two")

    def test_tokens_without_a_usable_lifetime_are_returned_but_never_cached(self):
        for expires_in in (1, 0, -30, None):
            with self.subTest(expires_in=expires_in):
                self.script(token=[token_response("token-one", expires_in), token_response("token-two", expires_in)])

                self.assertEqual(self.get_token(), "token-one")
                self.assertEqual(self.get_token(), "token-two")

                self.assertEqual(len(self.fake.token_requests), 2)

    def test_numeric_string_lifetimes_are_accepted(self):
        body = json.dumps({"access_token": "token-one", "expires_in": "3599"}).encode()
        self.script(token=HttpResponse(200, {}, body))

        self.assertEqual(self.get_token(), "token-one")
        self.assertEqual(self.get_token(), "token-one")

        self.assertEqual(len(self.fake.token_requests), 1)

    def test_different_certificate_tenant_or_client_id_use_separate_cache_entries(self):
        variants = {
            "certificate and key version": {"credential": self.other_credential},
            "thumbprint": {"x5t_s256": self.other_credential.x5t_s256},
            "tenant": {"tenant_id": "contoso.onmicrosoft.com"},
            "client id": {"client_id": "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"},
        }
        for label, overrides in variants.items():
            with self.subTest(label):
                self.script(token=[token_response("token-one"), token_response("token-two")])

                self.assertEqual(self.get_token(), "token-one")
                self.assertEqual(self.get_token(**overrides), "token-two")
                self.assertEqual(self.get_token(), "token-one")
                self.assertEqual(self.get_token(**overrides), "token-two")

                self.assertEqual(len(self.fake.token_requests), 2)

    def test_forget_access_token_drops_only_the_matching_entry(self):
        self.script(token=[token_response("token-a1"), token_response("token-b1"), token_response("token-a2")])
        self.assertEqual(self.get_token(), "token-a1")
        self.assertEqual(self.get_token(credential=self.other_credential), "token-b1")

        auth.forget_access_token(self.credential)

        self.assertEqual(self.get_token(credential=self.other_credential), "token-b1")
        self.assertEqual(self.get_token(), "token-a2")

    def test_forgetting_a_credential_that_was_never_cached_is_harmless(self):
        auth.forget_access_token(self.other_credential)

        self.assertEqual(self.get_token(), ACCESS_TOKEN)

    def test_clear_access_token_cache_forgets_every_entry(self):
        self.script(token=[token_response("token-a1"), token_response("token-b1"), token_response("token-a2")])
        self.get_token()
        self.get_token(credential=self.other_credential)

        auth.clear_access_token_cache()

        self.assertEqual(self.get_token(), "token-a2")
        self.assertEqual(len(self.fake.token_requests), 3)

    def test_cache_keys_name_the_pinned_version_and_never_contain_key_material(self):
        self.get_token()

        ((key, (token, _expiry)),) = auth._cache.items()
        self.assertEqual(key, (TENANT_ID, CLIENT_ID, self.credential.key_version_id, self.credential.x5t_s256))
        self.assertEqual(token, ACCESS_TOKEN)
        for line in private_key_lines():
            self.assertNotIn(line, repr(list(auth._cache)))
