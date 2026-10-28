"""Graph access tokens: the client-credentials request, the in-memory cache and failure classification."""

import json
from unittest.mock import patch
from urllib.parse import parse_qs

from django.test import SimpleTestCase

from apps.core.services.email import EmailDeliveryError, PermanentEmailDeliveryError, TransientEmailDeliveryError
from apps.core.services.email.graph import auth
from apps.core.services.email.graph.transport import ConnectFailed, HttpResponse, ResponseLost
from apps.core.tests.services.test_email_graph import (
    ACCESS_TOKEN,
    CLIENT_ID,
    CLIENT_SECRET,
    RESPONSE_TEXT,
    TENANT_ID,
    GraphFixtureMixin,
    token_response,
)


class FakeClock:
    """Replaces the ``time`` module inside ``auth`` so cache expiry can be driven without sleeping."""

    def __init__(self, now=1000.0):
        self.now = now

    def monotonic(self):
        return self.now


class TokenTestCase(GraphFixtureMixin, SimpleTestCase):
    def get_token(self, **overrides):
        values = {"tenant_id": TENANT_ID, "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET}
        return auth.get_access_token(**{**values, **overrides})


class GraphTokenRequestTests(TokenTestCase):
    def test_posts_the_client_credentials_grant_to_the_tenant_token_endpoint(self):
        self.assertEqual(self.get_token(), ACCESS_TOKEN)

        (request,) = self.fake.requests
        self.assertEqual(request.host, "login.microsoftonline.com")
        self.assertEqual(request.path, f"/{TENANT_ID}/oauth2/v2.0/token")
        self.assertEqual(request.headers["Content-Type"], "application/x-www-form-urlencoded")
        form = parse_qs(request.body.decode("ascii"), strict_parsing=True)
        self.assertEqual(
            form,
            {
                "client_id": [CLIENT_ID],
                "client_secret": [CLIENT_SECRET],
                "scope": ["https://graph.microsoft.com/.default"],
                "grant_type": ["client_credentials"],
            },
        )

    def test_the_secret_travels_only_in_the_form_body(self):
        self.get_token()

        request = self.fake.requests[0]
        self.assertNotIn(CLIENT_SECRET, request.path)
        self.assertNotIn(CLIENT_SECRET, "".join(request.headers.values()))
        self.assertNotIn("Authorization", request.headers)

    def test_special_characters_in_the_secret_are_url_encoded(self):
        secret = "p@ss&w=rd+1%2F /\N{LATIN SMALL LETTER E WITH ACUTE}\"'"

        self.get_token(client_secret=secret)

        body = self.fake.requests[0].body
        self.assertEqual(parse_qs(body.decode("ascii"), strict_parsing=True)["client_secret"], [secret])
        self.assertEqual(body.count(b"&"), 3, "the secret must not add form fields")
        self.assertNotIn(secret.encode(), body)

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
        self.assertEqual(self.fake.requests[0].timeout, auth.REQUEST_TIMEOUT)

        self.script()
        self.get_token(timeout=7)
        self.assertEqual(self.fake.requests[0].timeout, 7)


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

    def test_different_secret_tenant_or_client_id_use_separate_cache_entries(self):
        variants = {
            "secret": {"client_secret": "another-fake-secret"},
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
        self.assertEqual(self.get_token(client_secret="secret-a"), "token-a1")
        self.assertEqual(self.get_token(client_secret="secret-b"), "token-b1")

        auth.forget_access_token(TENANT_ID, CLIENT_ID, "secret-a")

        self.assertEqual(self.get_token(client_secret="secret-b"), "token-b1")
        self.assertEqual(self.get_token(client_secret="secret-a"), "token-a2")

    def test_forgetting_a_credential_that_was_never_cached_is_harmless(self):
        auth.forget_access_token(TENANT_ID, CLIENT_ID, "never-used-secret")

        self.assertEqual(self.get_token(), ACCESS_TOKEN)

    def test_clear_access_token_cache_forgets_every_entry(self):
        self.script(token=[token_response("token-a1"), token_response("token-b1"), token_response("token-a2")])
        self.get_token(client_secret="secret-a")
        self.get_token(client_secret="secret-b")

        auth.clear_access_token_cache()

        self.assertEqual(self.get_token(client_secret="secret-a"), "token-a2")
        self.assertEqual(len(self.fake.token_requests), 3)

    def test_cache_keys_do_not_contain_the_client_secret(self):
        self.get_token()

        self.assertEqual(len(auth._cache), 1)
        self.assertNotIn(CLIENT_SECRET, repr(list(auth._cache)))


class GraphTokenFailureTests(TokenTestCase):
    def assert_message_is_clean(self, error):
        for leaked in (RESPONSE_TEXT, CLIENT_SECRET, ACCESS_TOKEN, "trace-id-value"):
            self.assertNotIn(leaked, str(error))

    def test_transport_failures_are_classified_before_any_mail_is_sent(self):
        cases = [
            ("unreachable", ConnectFailed(), TransientEmailDeliveryError, "could not be reached"),
            (
                "tls verification",
                ConnectFailed(verification_failed=True),
                PermanentEmailDeliveryError,
                "TLS verification",
            ),
            ("no answer", ResponseLost(), TransientEmailDeliveryError, "did not answer"),
        ]
        for label, failure, expected, fragment in cases:
            with self.subTest(label):
                self.script(token=failure)

                with self.assertRaises(expected) as caught:
                    self.get_token()

                self.assertIn(fragment, str(caught.exception))
                self.assertIs(caught.exception.__cause__, failure)

    def test_rejected_credentials_are_permanent_and_name_only_the_error_codes(self):
        body = json.dumps(
            {
                "error": "invalid_client",
                "error_description": f"AADSTS7000215: Invalid client secret provided. {RESPONSE_TEXT}",
                "error_codes": [7000215],
                "trace_id": "trace-id-value",
                "correlation_id": "correlation-id-value",
            }
        ).encode()
        for status in (400, 401, 403):
            with self.subTest(status=status):
                self.script(token=HttpResponse(status, {}, body))

                with self.assertRaises(PermanentEmailDeliveryError) as caught:
                    self.get_token()

                self.assertIn("invalid_client AADSTS7000215", str(caught.exception))
                self.assert_message_is_clean(caught.exception)
                self.assertNotIn("Invalid client secret", str(caught.exception))
                self.assertNotIn("correlation-id-value", str(caught.exception))

    def test_a_rejection_without_a_readable_body_carries_no_code(self):
        for body in (b"", b"not json", b"[]", b'{"error": {"nested": "object"}}'):
            with self.subTest(body=body):
                self.script(token=HttpResponse(401, {}, body))

                with self.assertRaises(PermanentEmailDeliveryError) as caught:
                    self.get_token()

                self.assertEqual(str(caught.exception), "Microsoft rejected the Graph credentials.")

    def test_throttling_and_outages_are_transient_and_carry_retry_after(self):
        cases = [
            (408, {"retry-after": "5"}, 5.0),
            (429, {"retry-after": "45"}, 45.0),
            (429, {}, None),
            (500, {}, None),
            (503, {"retry-after": "3600"}, 3600.0),
            (503, {"retry-after": "99999"}, 3600.0),
        ]
        for status, headers, retry_after in cases:
            with self.subTest(status=status, headers=headers):
                self.script(token=HttpResponse(status, headers, f'{{"error": "{RESPONSE_TEXT}"}}'.encode()))

                with self.assertRaises(TransientEmailDeliveryError) as caught:
                    self.get_token()

                self.assertEqual(caught.exception.retry_after, retry_after)
                self.assert_message_is_clean(caught.exception)

    def test_unreadable_success_bodies_are_transient(self):
        bodies = {
            "not json": b"<html>Bad gateway</html>",
            "empty": b"",
            "invalid utf-8": b"\xff\xfe\x00garbage",
            "json list": b"[]",
            "json null": b"null",
            "json string": b'"token"',
            "missing token": b'{"expires_in": 3599}',
            "empty token": b'{"access_token": "", "expires_in": 3599}',
            "null token": b'{"access_token": null, "expires_in": 3599}',
            "non-string token": b'{"access_token": 12345, "expires_in": 3599}',
            "non-numeric lifetime": b'{"access_token": "token-one", "expires_in": "soon"}',
            "null lifetime": b'{"access_token": "token-one", "expires_in": null}',
        }
        for label, body in bodies.items():
            with self.subTest(label):
                self.script(token=HttpResponse(200, {}, body))

                with self.assertRaisesMessage(TransientEmailDeliveryError, "unreadable"):
                    self.get_token()

    def test_only_a_200_answer_can_provide_a_token(self):
        usable_looking_body = token_response().body
        for status in (201, 202, 204, 302):
            with self.subTest(status=status):
                self.script(token=[HttpResponse(status, {}, usable_looking_body), token_response("token-one")])

                with self.assertRaises(EmailDeliveryError):
                    self.get_token()

                # Nothing from the refused answer was cached, so the next call asks again.
                self.assertEqual(self.get_token(), "token-one")
                self.assertEqual(len(self.fake.token_requests), 2)

    def test_failures_are_not_cached(self):
        self.script(token=[HttpResponse(503, {}, b""), token_response("token-one")])

        with self.assertRaises(TransientEmailDeliveryError):
            self.get_token()

        self.assertEqual(self.get_token(), "token-one")
        self.assertEqual(len(self.fake.token_requests), 2)


class GraphTokenHardeningTests(TokenTestCase):
    def test_tokens_that_cannot_be_a_header_value_are_rejected_without_being_echoed(self):
        bad_tokens = {
            "newline": "abc\ndef",
            "carriage return": "abc\rdef",
            "space": "abc def",
            "non-ascii": "abc\N{LATIN SMALL LETTER E WITH ACUTE}def",
            "control character": "abc\x00def",
            "too long": "a" * 16385,
        }
        for label, token in bad_tokens.items():
            with self.subTest(label):
                body = json.dumps({"access_token": token, "expires_in": 3599}).encode()
                self.script(token=HttpResponse(200, {}, body))

                with self.assertRaisesMessage(TransientEmailDeliveryError, "unreadable") as caught:
                    self.get_token()

                self.assertNotIn(token, str(caught.exception))

    def test_jwt_and_opaque_token_alphabets_are_accepted(self):
        for token in ("eyJhbGciOiJSUzI1NiJ9.eyJhdWQiOiJ4In0.c2lnbmF0dXJl", "EwBwA+l3/BAAU==", "a-b_c~d.e"):
            with self.subTest(token):
                self.script(token=token_response(token))

                self.assertEqual(self.get_token(), token)

    def test_hostile_answers_are_classified_instead_of_escaping(self):
        bodies = {
            "deeply nested": b"[" * 70_000,
            "infinite lifetime": b'{"access_token": "token-one", "expires_in": 1e999}',
            "NaN lifetime": b'{"access_token": "token-one", "expires_in": NaN}',
        }
        for label, body in bodies.items():
            with self.subTest(label):
                self.script(token=HttpResponse(200, {}, body))

                with self.assertRaisesMessage(TransientEmailDeliveryError, "unreadable"):
                    self.get_token()

    def test_absurd_lifetimes_are_clamped_to_a_day(self):
        body = ('{"access_token": "token-one", "expires_in": ' + "9" * 400 + "}").encode()
        clock = FakeClock()
        with patch.object(auth, "time", clock):
            self.script(token=HttpResponse(200, {}, body))
            self.get_token()
            clock.now += auth.MAX_LIFETIME_SECONDS - auth.EXPIRY_MARGIN_SECONDS - 1

            self.get_token()
            self.assertEqual(len(self.fake.token_requests), 1)

            clock.now += 2
            self.get_token()
            self.assertEqual(len(self.fake.token_requests), 2)
