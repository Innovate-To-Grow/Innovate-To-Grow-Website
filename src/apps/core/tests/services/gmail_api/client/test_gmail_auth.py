"""The Gmail API token exchange: the request, the per-process cache, the answer checks and Google's refusals."""

from unittest.mock import patch
from urllib.parse import parse_qs

import jwt
from django.test import TestCase

from apps.core.services.email import PermanentEmailDeliveryError, TransientEmailDeliveryError
from apps.core.services.email.gmail.client import auth
from apps.core.services.email.gmail.client.access import credential_for, require_subject
from apps.core.services.email.gmail.service_account import stored_key
from apps.core.services.email.sending.transport import HttpResponse
from apps.core.tests.gmail_api_helpers import (
    SUBJECT,
    TOKEN,
    FakePost,
    reset_gmail_state,
    stored_config,
    token_response,
)

SENTINEL = "SENTINEL-c0ffee-must-never-be-echoed"


class GmailAuthTestCase(TestCase):
    def setUp(self):
        reset_gmail_state()
        self.config = stored_config()
        self.credential = credential_for(self.config)
        self.subject = require_subject(self.config, SUBJECT)

    def token(self, *answers):
        self.post = FakePost(*answers).install(self)
        return auth.get_access_token(self.credential, self.subject)

    def read_spy(self):
        patcher = patch.object(stored_key, "read_key", wraps=stored_key.read_key)
        spy = patcher.start()
        self.addCleanup(patcher.stop)
        return spy


class TokenRequestTests(GmailAuthTestCase):
    def test_form_body_host_and_path_are_exact(self):
        self.assertEqual(self.token(token_response()), (TOKEN, True))
        (call,) = self.post.calls
        self.assertEqual((call["host"], call["path"]), ("oauth2.googleapis.com", "/token"))
        self.assertEqual(call["headers"]["Content-Type"], "application/x-www-form-urlencoded")
        form = parse_qs(call["body"].decode("ascii"), strict_parsing=True)
        self.assertEqual(set(form), {"grant_type", "assertion"})
        self.assertEqual(form["grant_type"], ["urn:ietf:params:oauth:grant-type:jwt-bearer"])
        claims = jwt.decode(form["assertion"][0], options={"verify_signature": False})
        self.assertEqual((claims["sub"], claims["scope"]), (SUBJECT, "https://www.googleapis.com/auth/gmail.send"))
        self.assertEqual(call["timeout"], 15)

    def test_a_cache_hit_performs_zero_store_reads(self):
        self.token(token_response())
        spy = self.read_spy()
        self.assertEqual(auth.get_access_token(self.credential, self.subject), (TOKEN, False))
        spy.assert_not_called()
        self.assertEqual(len(self.post.calls), 1)

    def test_a_new_key_version_misses_the_cache(self):
        self.token(token_response(), token_response())
        rotated = auth.GmailCredential(**{**self.credential.__dict__, "key_version_id": self.config.key_version_id})
        self.assertEqual(auth.get_access_token(rotated, self.subject)[1], False)
        moved = auth.GmailCredential(**{**self.credential.__dict__, "key_version_id": "0" * 36})
        with self.assertRaises(PermanentEmailDeliveryError):
            auth.get_access_token(moved, self.subject)  # a miss: it reads the store, which holds no such version

    def test_ttl_keeps_a_margin_and_long_lifetimes_are_capped(self):
        with patch.object(auth.time, "monotonic", return_value=1000.0):
            self.token(token_response(expires_in=999_999), token_response())
        with patch.object(auth.time, "monotonic", return_value=1000.0 + 3600 - 300 - 1):
            self.assertFalse(auth.get_access_token(self.credential, self.subject)[1])
        with patch.object(auth.time, "monotonic", return_value=1000.0 + 3600 - 300 + 1):
            self.assertTrue(auth.get_access_token(self.credential, self.subject)[1])

    def test_a_short_lifetime_is_cached_for_half_of_it(self):
        with patch.object(auth.time, "monotonic", return_value=0.0):
            self.token(token_response(expires_in=400), token_response())
        with patch.object(auth.time, "monotonic", return_value=199.0):
            self.assertFalse(auth.get_access_token(self.credential, self.subject)[1])
        with patch.object(auth.time, "monotonic", return_value=201.0):
            self.assertTrue(auth.get_access_token(self.credential, self.subject)[1])

    def test_scope_and_token_type_checks(self):
        broader = "https://www.googleapis.com/auth/gmail.send https://mail.google.com/"
        for answer, expected in (
            (token_response(scope=broader), PermanentEmailDeliveryError),
            (token_response(scope="https://mail.google.com/"), PermanentEmailDeliveryError),
            (token_response(token_type="mac"), PermanentEmailDeliveryError),
            (HttpResponse(status=200, headers={}, body=b"{not json"), TransientEmailDeliveryError),
            (HttpResponse(status=200, headers={}, body=b'{"access_token": "a b"}'), TransientEmailDeliveryError),
        ):
            with self.subTest(body=answer.body[:60]), self.assertRaises(expected):
                auth.clear_access_token_cache()
                self.token(answer)
        auth.clear_access_token_cache()
        self.assertEqual(self.token(token_response(scope=None)), (TOKEN, True))

    def test_a_subject_built_without_the_allow_list_check_is_refused_before_any_read(self):
        spy = self.read_spy()
        self.post = FakePost().install(self)
        for forged in (auth.AllowedSubject(SUBJECT), SUBJECT):
            with self.subTest(forged=forged), self.assertRaises(TypeError):
                auth.get_access_token(self.credential, forged)
        spy.assert_not_called()
        self.assertEqual(self.post.calls, [])
