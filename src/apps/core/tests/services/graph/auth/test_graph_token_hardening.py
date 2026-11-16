import json
from unittest.mock import patch

from django.conf import settings

from apps.core.services.email import TransientEmailDeliveryError
from apps.core.services.email.graph.identity import auth
from apps.core.services.email.graph.transport import HttpResponse
from apps.core.tests.services.graph.auth.test_email_graph_auth import FakeClock, TokenTestCase
from apps.core.tests.services.graph.provider.test_email_graph import token_response


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
            clock.now += settings.GRAPH_TOKEN_MAX_LIFETIME_SECONDS - settings.GRAPH_TOKEN_EXPIRY_MARGIN_SECONDS - 1

            self.get_token()
            self.assertEqual(len(self.fake.token_requests), 1)

            clock.now += 2
            self.get_token()
            self.assertEqual(len(self.fake.token_requests), 2)
