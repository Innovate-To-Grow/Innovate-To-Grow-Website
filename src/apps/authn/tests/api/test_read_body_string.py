"""``read_body_string``: what a credential-exchange view may pass on to the database as a token."""

import json
from types import SimpleNamespace

from django.core.cache import cache
from django.http import QueryDict
from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from apps.authn.models import ImpersonationToken
from apps.authn.views.helpers import MAX_CREDENTIAL_LENGTH, read_body_string
from apps.mail.models import LoginLinkToken


def read(data, key="token"):
    return read_body_string(SimpleNamespace(data=data), key)


class ReadBodyStringTests(SimpleTestCase):
    def test_returns_the_stripped_string(self):
        self.assertEqual(read({"token": "  abc-DEF_123  "}), "abc-DEF_123")

    def test_reads_the_requested_key(self):
        self.assertEqual(read({"refresh": "r", "token": "t"}, "refresh"), "r")

    def test_form_encoded_bodies_still_work(self):
        self.assertEqual(read(QueryDict("token=abc%20def")), "abc def")

    def test_absent_blank_and_non_string_values_read_as_missing(self):
        for label, data in {
            "absent": {},
            "empty": {"token": ""},
            "blank": {"token": " \t\n "},
            "null": {"token": None},
            "number": {"token": 123},
            "boolean": {"token": True},
            "list": {"token": ["a"]},
            "object": {"token": {"a": 1}},
            "null body": None,
            "list body": ["token"],
            "string body": "token",
            "number body": 123,
        }.items():
            with self.subTest(data=label):
                self.assertEqual(read(data), "")

    def test_strings_the_database_cannot_take_read_as_missing(self):
        for label, value in {
            "lone high surrogate": "\ud800",
            "lone low surrogate": "\udfff",
            "surrogate inside text": "abc\ud800def",
            "NUL": "\x00",
            "NUL inside text": "abc\x00def",
            "NUL after whitespace": "  \x00  ",
        }.items():
            with self.subTest(value=label):
                self.assertEqual(read({"token": value}), "")

    def test_non_ascii_text_is_kept(self):
        # Anything that encodes as UTF-8 (accents, astral-plane characters) is not "unusable".
        self.assertEqual(read({"token": " tökén-\U0001f511 "}), "tökén-\U0001f511")

    def test_string_of_exactly_the_limit_is_kept_and_one_more_character_reads_as_missing(self):
        at_limit = "a" * MAX_CREDENTIAL_LENGTH

        self.assertEqual(read({"token": at_limit}), at_limit)
        self.assertEqual(read({"token": at_limit + "a"}), "")

    def test_the_limit_applies_to_the_stripped_value(self):
        at_limit = "a" * MAX_CREDENTIAL_LENGTH

        self.assertEqual(read({"token": f"  \t{at_limit}\n "}), at_limit)
        self.assertEqual(read({"token": f"  {at_limit}a  "}), "")

    def test_absurdly_long_values_read_as_missing(self):
        form = QueryDict(mutable=True)
        form["token"] = "a" * (MAX_CREDENTIAL_LENGTH + 1)

        self.assertEqual(read({"token": "a" * (3 * 1024 * 1024)}), "")
        self.assertEqual(read(form), "")

    def test_limit_leaves_wide_headroom_over_every_real_credential(self):
        """The cap must never be able to reject a genuine token: the longest one is a fraction of it."""
        login_link_token = LoginLinkToken.generate_token()
        real_lengths = {
            "login-link column": LoginLinkToken._meta.get_field("token").max_length,
            "impersonation column": ImpersonationToken._meta.get_field("token").max_length,
            "generated login-link token": len(login_link_token),
            "generated impersonation token": len(ImpersonationToken.generate_token()),
        }
        for label, length in real_lengths.items():
            with self.subTest(credential=label):
                self.assertLessEqual(length * 4, MAX_CREDENTIAL_LENGTH)

        self.assertEqual(read({"token": login_link_token}), login_link_token)


class CredentialEndpointLengthLimitTests(APITestCase):
    """Every view that reads its credential through ``read_body_string`` answers an absurd one like a missing one."""

    # label -> (url, the detail the endpoint gives for a well-sized token it does not know, i.e. one it looked up)
    ENDPOINTS = {
        "login-link": ("/mail/login-link/", "Invalid login link."),
        "magic-login alias": ("/mail/magic-login/", "Invalid login link."),
        "impersonate-login": ("/authn/impersonate-login/", "Invalid impersonation link."),
    }
    TOKEN_REQUIRED = "Token is required."

    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()

    def post_token(self, url, token):
        return self.client.post(url, json.dumps({"token": token}), content_type="application/json")

    def test_megabyte_long_token_is_answered_like_a_missing_one_without_reaching_the_database(self):
        huge = "a" * (1024 * 1024)  # under Django's 2.5 MB request-body cap, so the view itself must refuse it

        for label, (url, _) in self.ENDPOINTS.items():
            with self.subTest(endpoint=label):
                with self.assertNumQueries(0):
                    response = self.post_token(url, huge)

                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.data["detail"], self.TOKEN_REQUIRED)

    def test_body_past_the_request_size_cap_is_answered_400_without_reaching_the_database(self):
        # DRF 3.18+ lets Django's DATA_UPLOAD_MAX_MEMORY_SIZE reject this before the view runs; older DRF parsed it
        # and the view refused the token. Either way: a 400 and no query.
        huge = "a" * (3 * 1024 * 1024)

        for label, (url, _) in self.ENDPOINTS.items():
            with self.subTest(endpoint=label):
                with self.assertNumQueries(0):
                    response = self.post_token(url, huge)

                self.assertEqual(response.status_code, 400)

    def test_token_at_the_limit_is_still_looked_up_and_one_character_more_is_not(self):
        for label, (url, invalid_detail) in self.ENDPOINTS.items():
            with self.subTest(endpoint=label):
                at_limit = self.post_token(url, "a" * MAX_CREDENTIAL_LENGTH)
                over_limit = self.post_token(url, "a" * (MAX_CREDENTIAL_LENGTH + 1))

                self.assertEqual(at_limit.status_code, 400)
                self.assertEqual(at_limit.data["detail"], invalid_detail)
                self.assertEqual(over_limit.status_code, 400)
                self.assertEqual(over_limit.data["detail"], self.TOKEN_REQUIRED)
